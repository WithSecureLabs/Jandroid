import os
import json
import fnmatch
import logging
import configparser
from neo4j_graph_handler import Neo4jGraphHandler
from common import *

GRAPH_NODES = 'nodes'
GRAPH_RELATIONSHIP = 'rel'
GRAPH_RELATIONSHIPS = 'relationships'
GRAPH_RELATIONSHIP_FROM = 'from'
GRAPH_RELATIONSHIP_TO = 'to'
GRAPH_RELATIONSHIP_NAME = 'relationship_name'
GRAPH_RELATIONSHIP_SPECIAL = 'special'
GRAPH_NODE_START = 'Start'
GRAPH_NODE_END = 'End'


class GraphHelperMain:
    """Class providing graphing helper functions for the main analysis."""

    def __init__(self, base_dir):
        """Sets paths, reads configurations and initialises graph.
        
        :param base_dir: string specifying location of script base directory
        """
        # Set paths.
        self.path_base_dir = base_dir

        # Get node identifier from config file.
        # The node identifier is a string that we use as the "primary"
        #  attribute for a node.
        self.path_config_file = os.path.join(
            self.path_base_dir,
            'config',
            'jandroid.conf'
        )
        config = configparser.ConfigParser()
        config.read(self.path_config_file)        
        self.node_identifier = 'nodename'
        if config.has_section('NEO4J'):
            if config.has_option('NEO4J', 'NODE_IDENTIFIER'):
                self.node_identifier = config['NEO4J']['NODE_IDENTIFIER']

    def fn_initialise_neo4j(self):
        # Start Graph Handler.
        self.inst_graph_handler = Neo4jGraphHandler(self.path_base_dir)
        self.inst_graph_handler.fn_initialise_graph()
    
        # Create uniqueness constraint on node identifier.
        # For this, we first need to set a common label for all apps.
        self.common_label = ':App'
        self.inst_graph_handler.fn_create_uniqueness_constraint(
            self.common_label,
            self.node_identifier
        )

    def fn_update_graph(self, app_name, graphables):
        """Updates the graph for a specific app, based on analysis output.
        
        The Android application analysis results in a dictionary object 
        being generated, with one key holding a list of graphable elements 
        for the application. 
        
        A single graphable element (i.e., one item from the list) corresponds 
        to the output from analysing the app against a single bug. A single 
        graphable element may actually consist of multiple nodes and 
        relationships (in the case of tracepaths). Note that the relationships 
        in this case are the links in tracepaths for a single bug, *not* links 
        between different bugs.
        
        This function calls other functions to process the graphables and 
        insert them into the neo4j graph.
        
        :param app_name: string name of the application or package
        :param graphables: list of graphable nodes and relationships
        """
        logging.info('Creating graph elements for ' + app_name + '.')

        # Get all node and relationship elements.    
        graphable_nodes = self.fn_get_graphable_nodes(graphables)
        if graphable_nodes == []:
            return
        # Send the combined node list to a handler to create graph nodes.
        self.fn_node_handler(graphable_nodes, app_name)
        
        graphable_relationships = self.fn_get_graphable_relationships(graphables)
        if graphable_relationships == []:
            return
        
        # Create relationships.
        self.fn_relationship_handler(graphable_relationships, app_name)

    def fn_get_graphable_nodes(self, graphables):
        all_nodes = []
        for per_bug_graph_element in graphables:
            # If there are no nodes corresponding to a bug, then there are
            #  obviously not going to be any relationships.
            if GRAPH_NODES not in per_bug_graph_element:
                continue
            
            # The nodes will be in a list, so we don't append, we concatenate.
            all_nodes = all_nodes + per_bug_graph_element[GRAPH_NODES]
        if all_nodes == []:
            return []
        return self.fn_combine_bugs_per_node(all_nodes)
        
    def fn_get_graphable_relationships(self, graphables):
        all_rels = []
        for per_bug_graph_element in graphables:
            if GRAPH_RELATIONSHIPS not in per_bug_graph_element:
                continue

            # The relationships are also in a list, so concatenate.
            all_rels = all_rels + per_bug_graph_element[GRAPH_RELATIONSHIPS]
        if all_rels == []:
            return []
        return self.fn_process_relationships(all_rels)
    
    def fn_combine_bugs_per_node(self, list_of_all_graphable_nodes):
        """Combines attributes and labels for bugs.
        
        A single node may satisfy multiple bugs. Rather than creating a node 
        for one bug and then adding additional labels and attributes as we go 
        through the graphables list, we combine all bugs for a node first, 
        and perform a single CREATE operation.
        
        This function identifies all possible node identifier values, and 
        creates keys within a dictionary object for each one. That is, the 
        dictionary object will have one key per node that is to be created. 
        The function then adds all relevant labels and attributes 
        corresponding to the node identifier to the dictionary object, and 
        calls another function to convert the dictionary object back to a 
        list that can be processed by the Neo4jGraphHandler.
 
        :param list_of_all_graphable_nodes: list of graphable objects
        :returns: list of combined graphable objects
        """
        temporary_graph_object = {}        
        for element in list_of_all_graphable_nodes:
            attribute_list = element['attributes']
            # Find node identifier value. Every node element will have
            #  this as an attribute.
            current_node_id = self.fn_identify_node_id(attribute_list)
            if current_node_id == None:
                continue
            current_node_id = current_node_id.strip()
            
            # Use the node identifier value as a key.
            if current_node_id not in temporary_graph_object:
                temporary_graph_object[current_node_id] = {
                    'attributes': {},
                    'labels': []
                }
        
        """
        At the end of this step, we have a dictionary object containing every 
        node identifier value as a key, and an attribute-label dictionary 
        object as the value. 
        Example:
            {
              'node_name1': {
                  'attributes': {},
                  'labels': []
              },
              'node_name2': {
                  'attributes': {},
                  'labels': []
              }
            }
        """
        
        # We now add the remaining attributes and labels for each key item.
        for element in list_of_all_graphable_nodes:
            # Get all the attributes.
            attribute_list = element['attributes']

            # Get the node identifier value again.
            current_node_id = self.fn_identify_node_id(attribute_list)
            if current_node_id == None:
                continue
            current_node_id = current_node_id.strip()
            
            # The attributes that are already present in the graph object
            #  (corresponding to a particular node id value).
            graph_attribute_object = \
                temporary_graph_object[current_node_id]['attributes']
            
            # Go through all attribute objects and add any that aren't already
            #  present.
            for attribute_obj in attribute_list:                
                for attribute_key in attribute_obj:
                    attribute_value = attribute_obj[attribute_key]
                    
                    # If the key is already present, then add the value if
                    #  the value is not present.
                    if attribute_key in graph_attribute_object:
                        if type(graph_attribute_object[attribute_key]) is str:
                            # If the value we want to add is the same as the
                            #  existing string, then skip.                            
                            existing_value = graph_attribute_object[attribute_key]
                            if attribute_value == existing_value:
                                continue
                            graph_attribute_object[attribute_key] = [existing_value]
                        if (attribute_value not in 
                                graph_attribute_object[attribute_key]):
                            graph_attribute_object[attribute_key].append(
                                attribute_value
                            )
                    # If the key is not present, create it and assign it 
                    #  the value. Do NOT automatically assign a list as this
                    #  will cause problems.
                    else:
                        graph_attribute_object[attribute_key] = \
                            attribute_value
            
            # Labels are a lot more straightforward. Simply add any label
            #  that isn't already present in the label list.
            # Existing labels.
            graph_label_list = \
                temporary_graph_object[current_node_id]['labels']
            # Labels to add.
            label_list = element['labels']
            for label in label_list:
                if label in graph_label_list:
                    continue
                graph_label_list.append(label)

        # Convert the graph object to list.
        new_graph_list = \
            self.fn_convert_graph_object_to_list(temporary_graph_object)
        return new_graph_list

    def fn_convert_graph_object_to_list(self, graph_obj):
        """Converts a graph object to list format.
        
        :param graph_obj: dictionary object containing a key per node 
            with all attributes (other than node identifier) and labels
        :returns: list of graphable elements corresponding to the graph_obj
        """
        graph_list = []
        # The graph list is essentially a list of dictionary objects, with
        #  keys for attributes and labels.
        for element in graph_obj:
            graph_list.append({
                'attributes': graph_obj[element]['attributes'],
                'labels': graph_obj[element]['labels']
            })
        return graph_list

    def fn_node_handler(self, graphable_nodes, app_name):
        """Retrieves graphable data; converts and adds to graph.
        
        :param graphable_nodes: a list of dictionary objects, containing 
            the keys 'labels' and 'attributes' with list values
        :param app_name: string name of the application or package, 
            added as an additional attribute for potential node merging
        """
        for element in graphable_nodes:
            # Add package name as an attribute.
            element['attributes']['package'] = app_name
            
            # Convert labels and attributes to Cypher representation.
            [attributes, labels] = self.fn_convert_to_cypher(element)
            
            # Create node for this app.
            try:
                self.inst_graph_handler.fn_create_node(attributes, labels)
            except JandroidException as e:
                # What do we do at this point?
                logging.error(
                    '['
                    + e.args[0]['type']
                    + '] '
                    + e.args[0]['reason']
                )
    
    def fn_convert_to_cypher(self, element):
        """Converts a dictionary object into a format suitable for Cypher.
        
        Neo4j requires labels and attributes to be specified in a certain 
        format. Labels must be prefixed by ":". Attributes must be presented 
        in a dictionary-like format, i.e., key:value.
        
        This function retrieves labels and attributes from an input object 
        and converts them into Cypher-suitable formats.
        
        Sample input:
            element = {
                'labels': [':Label1', ':Label2'],
                'attributes': {
                    'attr1': 'value1',
                    'attr2': ['value2-1', 'value2-2']
                }
            }
        The above input would product the following output:
            [
                ['attr1:"value1"', 'attr2:["value2-1","value2-2"]'],
                [':Label1', ':Label2']
            ]
        This output is in a format that can be handled by the Neo4jGraphHandler.
        
        :param element: dictionary object with the keys 'attributes' and 
            'labels', each of which contain a list of strings
        :returns: list containing a list of attributes and a list of labels
        :raises JandroidException: an exception is raised if attributes are 
            not dictionary objects
        """
        # First process labels. 
        # We create a set, to avoid duplicates without the need for a
        #  "if x not in <list>" check.
        labels = set()
        
        # Add the common label, needed for the uniqueness constraint.
        labels.add(self.common_label)
        
        # Add all input labels.
        for label in element['labels']:
            # If a label is not prefixed by ":", then add the prefix.
            if label[0] != ':':
                label = ':' + label
            labels.add(label)

        # We create a set, to avoid duplicates without the need for a
        #  "if x not in <list>" check.
        attributes = set()

        # Attributes should be in dictionary format.
        attribute_item = element['attributes']
        if type(attribute_item) is not dict:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': InvalidElementType',
                    'reason': '[fn_convert_to_cypher] attributes must be '
                              + 'dictionary.'
                }
            )

        # Convert each dictionary object into a string suitable for Cypher.
        # Note that attribute values can be lists or strings.
        for attribute_key in attribute_item:
            # If attribute values are in a list, then a little more processing
            #  is required.
            if type(attribute_item[attribute_key]) is list:
                cypher_attributes = \
                    self.fn_convert_attribute_list_to_cypherstring(
                        attribute_item[attribute_key]
                    )
                attribute_string = attribute_key \
                               + ':' \
                               + cypher_attributes
            elif type(attribute_item[attribute_key]) is str:
                attribute_string = attribute_key \
                               + ':"' \
                               + attribute_item[attribute_key] \
                               + '"'
            else:
                continue
            # Add the processed attribute string to the set of attributes.
            attributes.add(attribute_string)

        # Convert the sets to lists and return.
        return [list(attributes), list(labels)]

    def fn_convert_attribute_list_to_cypherstring(self, attribute_value_list):
        """Converts an attribute value list into Cypher format.
        
        Sample input:
            ['val1', 'val2']
        The above would produce the following output:
            '["val1","val2"]'
        
        :param attribute_value_list: attribute value list
        :returns: string representation of attribute value list
        """
        # String start.
        list_as_string = '['
        for attribute_value in attribute_value_list:
            # If the string contains only "[", it means no attribute value has
            #  yet been added. This means we don't need a comma-separation.
            if type(attribute_value) != type(""):
                attribute_value = ",".join(attribute_value[:-1])
            if list_as_string == '[':
                list_as_string = list_as_string + '"' + attribute_value + '"'
            else:
                list_as_string = list_as_string + ',"' + attribute_value + '"'
        # String end.
        list_as_string = list_as_string + ']'
        return list_as_string

    def fn_process_relationships(self, relationship_list):
        """Combines relationship attributes.
        
        If two nodes have two relationships of teh same type between them, 
        i.e., corresponding to two different bugs, then we want to collapse 
        the bugs onto a single relationship.
        
        :param relationship_list: list of dictionary objects with 
            relationship-specific fields (FROM, TO and RELATIONSHIP 
            name)
        :returns: list of relationships with combined bugs
        """
        rel_obj = {}
        for relationship_obj in relationship_list:
            # We create relationships between nodes that we identify solely
            #  via their node identifier value.
            from_identifying_value = self.fn_identify_node_id(
                relationship_obj[GRAPH_RELATIONSHIP_FROM]['attributes']
            )
            to_identifying_value = self.fn_identify_node_id(
                relationship_obj[GRAPH_RELATIONSHIP_TO]['attributes']
            )
            relationship_name = \
                relationship_obj[GRAPH_RELATIONSHIP][GRAPH_RELATIONSHIP_NAME]
            relationship_attributes = \
                relationship_obj[GRAPH_RELATIONSHIP]['attributes']
            rel_obj = self.fn_combine_relationship_attributes(
                rel_obj,
                from_identifying_value,
                to_identifying_value,
                relationship_name,
                relationship_attributes
            )

        # Convert back to list.
        new_relationship_list = \
            self.fn_convert_relationship_objs_to_list(rel_obj)
        return new_relationship_list

    def fn_identify_node_id(self, attribute_list):
        """Identifies the attribute value corresponding to the node identifier.
        
        :param attribute_list: list of dictionary objects representing
            attributes for a node
        :returns: attribute value corresponding to the node identifier, or 
            None if the node identifier was not present as a key
        """
        for attribute_obj in attribute_list:
            for attribute_key in attribute_obj:
                if attribute_key == self.node_identifier:
                    node_id_value = attribute_obj[attribute_key]
                    return node_id_value
        return None

    def fn_combine_relationship_attributes(self, rel_obj, from_val, to_val,
                                           rel_name, rel_attr_list):
        """Combines all attributes for a given relationship name.
        
        :param rel_obj: dictionary object, containing a nested structure 
            from->to->relationship_name->attributes
        :returns: updated rel_obj
        """
        if from_val not in rel_obj:
            rel_obj[from_val] = {}
        if to_val not in rel_obj[from_val]:
            rel_obj[from_val][to_val] = {}
        if rel_name not in rel_obj[from_val][to_val]:
            rel_obj[from_val][to_val][rel_name] = {}
            rel_obj[from_val][to_val][rel_name]['attributes'] = {}
        for attribute_obj in rel_attr_list:
            for attribute_name in attribute_obj:
                # This is just to reduce the object name length.
                temp_attr_obj = \
                    rel_obj[from_val][to_val][rel_name]['attributes']
                if (attribute_name not in temp_attr_obj):
                    temp_attr_obj[attribute_name] = []
                rel_attr_name = attribute_obj[attribute_name]
                if rel_attr_name not in temp_attr_obj[attribute_name]:
                    temp_attr_obj[attribute_name].append(rel_attr_name)

        # Return the updated object.
        return rel_obj
    
    def fn_convert_relationship_objs_to_list(self, rel_obj):
        """Converts a dictionary object representing a relationship to a list.
        
        :param rel_obj: dictionary object representing a relationship
        :returns: a list of standardised relationship objects usable by 
            the Neo4jGraphHandler
        """
        relationship_list = []
        for from_obj in rel_obj:
            for to_obj in rel_obj[from_obj]:
                for rel_name in rel_obj[from_obj][to_obj]:
                    # Create a relation string comprising the
                    #  relationship name and relationship attributes.
                    rel_string = self.fn_create_relationship_attribute_string(
                            rel_name,
                            rel_obj[from_obj][to_obj][rel_name]['attributes']
                        )
                    # Create the relationship object again.
                    single_rel_obj = {
                        GRAPH_RELATIONSHIP_FROM: {
                            'attributes': {
                                self.node_identifier: from_obj
                            },
                            'labels': []
                        },
                        GRAPH_RELATIONSHIP_TO:  {
                            'attributes': {
                                self.node_identifier: to_obj
                            },
                            'labels': []
                        },
                        GRAPH_RELATIONSHIP_NAME: rel_string
                    }
                    relationship_list.append(single_rel_obj)
        return relationship_list
    
    def fn_create_relationship_attribute_string(self, rel_name,
                                                rel_attr_list=None):
        """Creates a string of attributes associated with a relationship.
        
        :param rel_name: the string name of the relationship
        :param rel_attr_list: a list of dictionary objects, each corresponding 
            to a single attribute
        :returns: a string representation of the attributes in a format 
            suitable for the Neo4jGraphHandler
        """
        rel_string = rel_name
        if ((rel_attr_list == None) or (rel_attr_list == [])):
            return rel_string

        # Create a string of the attributes.
        attribute_string = '{'
        for attribute_key in rel_attr_list:
            attribute_value = str(rel_attr_list[attribute_key])
            if attribute_string == '{':
                attribute_string = attribute_string \
                                   + attribute_key \
                                   + ':' \
                                   + attribute_value
            else:
                attribute_string = attribute_string \
                                   + ',' \
                                   + attribute_key \
                                   + ':' \
                                   + attribute_value
        attribute_string = attribute_string + '}'
        rel_string = rel_string + ' ' + attribute_string
        return rel_string

    def fn_relationship_handler(self, graphable_relationships, app_name):
        """Processes graph relationship objects and adds to neo4j graph.
        
        This function retrieves data pertaining to a graph relationship 
        (i.e., a directional link between two nodes), calls other functions 
        to convert the data into a suitable format for the Neo4jGraphHandler, and 
        calls the Neo4jGraphHandler's relationship creation function.
        
        :param graphable_relationships: list of dictionary objects, where 
            each dictionary object contains keys for the FROM node, the 
            TO node, and the relationship name.
        :param app_name: string name of the application or package
        """
        # Process each individual relationship item (corresponding to a
        #  single link between two nodes).
        for relationship in graphable_relationships:
            # Convert the attributes and labels corresponding to the FROM node
            #  to a Cypher-suitable format.
            [from_attributes, from_labels] = self.fn_convert_to_cypher(
                relationship[GRAPH_RELATIONSHIP_FROM]
            )
            # Add the processed data to an object.
            from_object = {
                'attributes': list(from_attributes),
                'labels': list(from_labels)
            }
            
            # Convert the attributes and labels corresponding to the TO node
            #  to a Cypher-suitable format.
            [to_attributes, to_labels] = self.fn_convert_to_cypher(
                relationship[GRAPH_RELATIONSHIP_TO]
            )
            # Add the processed data to an object.
            to_object = {
                'attributes': list(to_attributes),
                'labels': list(to_labels)
            }
            
            # Call the relationship creation function, with the FROM object,
            #  TO object, and relationship name as arguments.
            try:
                self.inst_graph_handler.fn_create_relationship(
                    from_object,
                    to_object,
                    relationship[GRAPH_RELATIONSHIP_NAME]
                )
            except JandroidException as e:
                # What do we do at this point?
                logging.error(
                    '['
                    + e.args[0]['type']
                    + '] '
                    + e.args[0]['reason']
                )

    def fn_final_update_graph(self):
        """Enumerates link files and creates the links.
        
        Links between different bug types are specified using a .links file, 
        which must be present in the templates/ folder. 
        This function checks the templates/ folder for all .links files and 
        calls another function to process each file.
        """
        logging.info('Creating exploit links.')

        # Enumerate link files. These are also in the templates/ folder,
        #  within the android/ sub-folder.
        template_folder = os.path.join(
            self.path_base_dir,
            'templates',
            'android'
        )
        graph_link_files = []
        for root, _, filenames in os.walk(template_folder):
            for filename in fnmatch.filter(filenames, '*.links'):
                graph_link_files.append(os.path.join(root, filename))

        # If there are no link files, there's nothing to do.
        if graph_link_files == []:
            return

        # Call link creation function for each link file individually.
        for graph_link_file in graph_link_files:
            self.fn_process_individual_link_file(graph_link_file)
            
    def fn_process_individual_link_file(self, link_file):
        """Creates links between different bugs.
        
        Links between different bug types are specified in a "link file". 
        This is simply a file in JSON format, but with a .links extension.
        
        Sample .links file:
            {
                "Bug1": "Bug2Start",
                "Bug2End": "Bug3",
                "Bug3": ["Bug4Start", "Bug5"]
            }
            
        :param link_file: string representing path to link file location
        """        
        link_file_object = None
        # Open and load JSON file into dictionary object.
        with open(link_file, 'r') as link_file_input:
            link_file_object = json.load(link_file_input)
        if link_file_object == None:
            return

        # Create links using Neo4jGraphHandler's relationship creation function.
        # The bug_item is the label to be used for the FROM node, the
        #  linked_item(s) are the label(s) to be used for the TO node(s).
        for bug_item in link_file_object:
            for linked_item in link_file_object[bug_item]:
                # We use a single fixed relationship name.
                try:
                    self.inst_graph_handler.fn_create_relationship_from_labels(
                        bug_item, linked_item, ':EXPLOITS'
                    )
                except JandroidException as e:
                    # What do we do at this point?
                    logging.error(
                        '['
                        + e.args[0]['type']
                        + '] '
                        + e.args[0]['reason']
                    )