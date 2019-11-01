import os
import sys
import logging
import configparser
from neo4jrestclient.client import GraphDatabase
from common import JandroidException


class Neo4jGraphHandler:
    """Class containing some helper functions for neo4j graphing."""

    def __init__(self, base_dir):
        """Sets paths and reads in relevant config file parameters.

        Identifies the config file location with respect to the base 
        code directory. Opens config file and reads in graph-specific 
        config options (i.e., neo4j URL, username and password).

        :param base_dir: string specifying base directory for the code
        """
        # Get path to config file.
        path_config_file = os.path.join(
            base_dir,
            'config',
            'jandroid.conf'
        )
        # Read config file.
        config = configparser.ConfigParser()
        config.read(path_config_file)
        self.neo4j_url = 'http://localhost:7474'
        self.neo4j_username = 'neo4j'
        self.neo4j_password = 'n3o4j'
        if config.has_section('NEO4J'):
            if config.has_option('NEO4J', 'URL'):
                self.neo4j_url = config['NEO4J']['URL']
            if config.has_option('NEO4J', 'USERNAME'):
                self.neo4j_username = config['NEO4J']['USERNAME']
            if config.has_option('NEO4J', 'PASSWORD'):
                self.neo4j_password = config['NEO4J']['PASSWORD']

        # Initialise database connection object.
        self.db = None

    def fn_connect_to_graph(self):
        """Connects to Neo4j database.

        Creates a connection to the neo4j database, using the parameters 
        specified in the config file (or default values).

        :raises JandroidException: an exception is raised if connection to 
            neo4j database fails.
        """
        logging.info(
            'Trying to connect to Neo4j graph DB.'
        )
        try:
            self.db = GraphDatabase(
                self.neo4j_url,
                username=self.neo4j_username,
                password=self.neo4j_password
            )
            logging.info('Connected to graph DB.')
        except Exception as e:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': GraphConnectError',
                    'reason': 'Unable to connect to Neo4j '
                              + 'graph database. '
                              + 'Are you sure it\'s running? '
                              + 'Returned error is: '
                              + str(e)
                }
            )

    def fn_initialise_graph(self):
        """Initialises graph by removing all existing nodes/relationships."""
        # Connect to graph if not already connected.
        if self.db == None:
            self.fn_connect_to_graph()

        # Delete all existing nodes and relationships.
        delete_all_query = 'MATCH (n) DETACH DELETE n'
        _ = self.fn_execute_graph_query(delete_all_query)

    def fn_create_uniqueness_constraint(self, label, attribute):
        """Creates uniqueness constraint on an attribute for a label.
        
        This function creates a uniqueness constraint against all nodes 
        that have a particular label, requiring that the specified attribute 
        be unique.
        
        :param label: the label of the node(s) to create the constraint on
        :param attribute: the attribute to create the constraint on
        """
        # Labels in neo4j have ":" as the first character. If the given
        #  label doesn't have ":" as its first character, prepend ":".
        if label[0] != ':':
            label = ':' + label

        # Create graph query from inputs.
        uniqueness_constraint = 'CREATE CONSTRAINT ON (n' \
                                + label \
                                + ') ASSERT n.' \
                                + attribute \
                                + ' IS UNIQUE'

        # Execute graph query.
        constraint_query = self.fn_execute_graph_query(
            uniqueness_constraint
        )

    def fn_create_node_key(self, label, attributes):
        """Creates node key from attributes for a label.
        
        This function creates a node key from a group of attributes 
        against all nodes that have a particular label.
        
        :param label: the label of the node(s) to create the constraint on
        :param attributes: list<string> or string of attribute(s) for node key
        """
        # Labels in neo4j have ":" as the first character. If the given
        #  label doesn't have ":" as its first character, prepend ":".
        if label[0] != ':':
            label = ':' + label

        # Create query from inputs.
        uniqueness_constraint = 'CREATE CONSTRAINT ON (n' \
                                + label \
                                + ') ASSERT ('
        # We append each attribute individually.
        attribute_list = ''
        if type(attributes) is not list:
            attributes = [attributes]
        for attribute in attributes:
            if attribute_list == '':
                attribute_list = attribute_list + 'n.' + attribute
            else:
                attribute_list = attribute_list + ', n.' + attribute
        uniqueness_constraint = uniqueness_constraint \
                                + attribute_list \
                                + ') IS NODE KEY'

        # Execute graph query.
        constraint_query = self.fn_execute_graph_query(
            uniqueness_constraint
        )

    def fn_create_node(self, attributes=[], labels=[]):
        """Creates a node in neo4j graph with the given labels and attributes.
        
        The labels argument is a list of strings, where each label string 
        is prefixed by ":".
        The attributes argument is a list of strings in key:value format.
        
        Sample input:
            attributes = ['attr1:"value1"', 'attr2:["value2-1","value2-2"]']
            labels = [':Label1', ':Label2']
        
        :param attributes: list<string> of attributes in key:value format
        :param labels: list<string> of labels in :name format
        """
        # Query string.        
        graph_query = 'CREATE ' + self.fn_create_node_query_item(
            attributes,
            labels,
            'n'
        )

        # Execute graph query.
        self.fn_execute_graph_query(graph_query)

    def fn_create_relationship(self, start_node_obj, end_node_obj, rel_name):
        """Creates a relationship in neo4j graph between two existing nodes.
        
        :param start_node_obj: dictionary object with possible keys:
            'attributes' and 'labels' denoting the node to create the 
            relationship from
        :param end_node_obj: dictionary object with possible keys:
            'attributes' and 'labels' denoting the node to create the 
            relationship to
        :param rel_name: name for the relationship
        """
        # Retrieve attributes and labels as list from the input objects
        #  for start and end objects.
        [start_node_attributes, start_node_labels] = \
            self.fn_get_attributes_labels(start_node_obj)   
        start_node_match_string = self.fn_create_match_query(
            start_node_attributes,
            start_node_labels,
            'n'
        )
        [end_node_attributes, end_node_labels] = \
            self.fn_get_attributes_labels(end_node_obj)
        end_node_match_string = self.fn_create_match_query(
            end_node_attributes,
            end_node_labels,
            'm'
        )
        
        # Relationship names must begin with ":". If the specified
        #  relationship does not, then prepend ":".
        if rel_name[0] != ':':
            rel_name = ':' + rel_name

        # Create the database query.
        relation_query = start_node_match_string \
                         + ' ' \
                         + end_node_match_string \
                         + ' ' \
                         + 'MERGE (n)-[' \
                         + rel_name \
                         + ']->(m) ' \
                         + 'RETURN n, m'

        # Execute database query.
        self.fn_execute_graph_query(relation_query)

    def fn_create_relationship_from_labels(self, start_label,
                                           end_label, rel_name):
        """Creates a relationship between nodes having specific labels.
        
        :param start_label: label string for start node
        :param end_label: label string for end node
        :param rel_name: name for the relationship
        """
        # Labels and relationship names must begin with ":". 
        # If the specified labels/relationships do not, then prepend ":".
        if start_label[0] != ':':
            start_label = ':' + start_label
        if end_label[0] != ':':
            end_label = ':' + end_label
        if rel_name[0] != ':':
            rel_name = ':' + rel_name

        # Create the database query.
        relation_query = 'MATCH (n' \
                         + start_label \
                         + ') ' \
                         + 'MATCH (m' \
                         + end_label \
                         + ') ' \
                         + 'CREATE (n)-[' \
                         + rel_name \
                         + ']->(m) ' \
                         + 'RETURN n, m'

        # Execute the database query.
        self.fn_execute_graph_query(relation_query)

    def fn_get_attributes_labels(self, object):
        """Retrieves attributes and labels from object.
        
        This function takes as input a dictionary object containing 
        (at least) two keys: "attributes" and "labels".
        It retrieves the attributes and labels and returns them
        as lists within a list.
        
        :param object: dictionary object containing keys:
            "attributes" and "labels"
        :returns: list containing two lists: one of attributes,
            one of labels
        """
        if 'attributes' in object:
            node_attributes = object['attributes']
        else:
            node_attributes = []
        if 'labels' in object:
            node_labels = object['labels']
        else:
            node_labels = []
        if ((node_attributes == []) and
                (node_labels == [])):
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': EmptyAttributeAndLabelList',
                    'reason': 'A node must have at least '
                              + 'one attribute or label.'
                }
            )
        return [node_attributes, node_labels]

    def fn_create_match_query(self, attributes, labels, id='n'):
        """Creates a Cypher MATCH query for node from attributes and labels.
        
        This function takes as input attributes and labels for a node 
        (and optionally an identifier), and returns a Cypher MATCH query.
        e.g., if the function is called with 
            self.fn_create_match_query(['att1:"val1"'], [':Label1'], 'm')
        the output will be
            'MATCH (m:Label1 {att1:"val1"})'

        :param attributes: list<string> of attributes in key:value format
        :param labels: list<string> of labels 
        :param id: node identifier string; default value is "n"
        :returns: MATCH query as string
        """
        match_string = 'MATCH ' + self.fn_create_node_query_item(
            attributes,
            labels,
            id
        )
        return match_string

    def fn_create_node_query_item(self, attributes, labels, id='n'):
        """Creates a string representing a node from attributes and labels.
        
        This function takes as input a list of attributes and labels 
        (and optionally, a node identifier), and returns a string representing 
        the node.
        e.g., if the function is called with
            self.fn_create_node_query_item(['att1:"val1"'], [':Label1'], 'm')
        it will return
            '(m:Label1 {att1:"val1"})'

        :param attributes: list<string> of attributes in key:value format
        :param labels: list<string> of labels 
        :param id: node identifier string; default value is "n"
        :returns: Node representation string
        """
        # Query string start.        
        node_string = '(' + id

        # Add all labels.
        for label in labels:
            node_string = node_string + label

        # Add attributes. Attributes need a bit more processing because
        #  of the way they need to be specified.
        if attributes != []:
            attribute_string = ''
            for attribute in attributes:
                if attribute_string == '':
                    attribute_string = attribute
                else:
                    attribute_string = attribute_string + ',' + attribute
            # Add attribute part to graph query.
            node_string = node_string + ' {' + attribute_string + '}'

        # Close query string.        
        node_string = node_string +')'
        
        return node_string

    def fn_execute_graph_query(self, cypher_query):
        """Executes the provided Cypher query against a neo4j graph.
        
        :param cypher_query: the Cypher query to execute against the 
            neo4j graph
        :raises JandroidException: an exception is raised if query fails to 
            execute
        """
        try:
            res = self.db.query(cypher_query)
        except Exception as e:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': DBQueryError',
                    'reason': str(e)
                }
            )
        logging.debug(
            'Executed query "'
            + cypher_query
            + '" with result stats: '
            + str(res.stats)
            + ' and values: '
            + str(res.rows)
        )
        return res