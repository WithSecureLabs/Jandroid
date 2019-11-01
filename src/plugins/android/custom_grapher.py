import os
import sys
import json
import random
import fnmatch
import logging
import configparser
from graph_helper_main import GraphHelperMain


class CustomGrapher:
    """Class for creating vis.js graphs from analyser output.
    
    This class contains methods that essentially build up an HTML file 
    with vis.js functionality to display, colour and filter a custom graph.
    """
    
    def __init__(self):
        """Initialises variables."""
        self.html_content = ''
        self.nodes = []
        self.start_node_ids = []
        self.end_node_ids = []
        self.edges = []
        self.links = {}
        self.app_ids = {}
        self.edge_counter = 0
        self.node_identifier = 'nodename'
        
    def fn_create_custom_graph(self, base_dir, analysis_output):
        """Calls multiple functions to create various parts of HTML file.
        
        Once the HTML file has been created within this class, it is written
        out to the output->graph directory.
        
        :param base_dir: string denoting path to base directory
        :param analysis_output: dictionary object containing the output of 
            the Jandroid analysis
        """
        logging.info('Creating custom graph.')
        # Initialise variables.
        self.existing_node_ids = []
        self.inst_graph_helper_main = GraphHelperMain(base_dir)
        self.fn_initialise_links(base_dir)
        self.fn_get_node_identifier(base_dir)
        # Process graphable elements and create vis.js components.
        self.fn_enumerate_bugs(analysis_output)        
        self.fn_process_analysis_object(analysis_output)
        # HTML generation.
        self.fn_begin_html_content()
        self.fn_initialise_colours()
        self.fn_add_node_dataset()
        self.fn_add_edge_dataset()
        self.fn_create_network()
        self.fn_add_onclick_script()
        self.fn_add_ondoubleclick_script()
        self.fn_add_nodefilter()
        self.fn_add_clearfilters()
        self.fn_add_redraw()
        self.fn_add_select_node()
        self.fn_add_highlightstart()
        self.fn_add_highlightend()
        self.fn_add_node_colourer()
        self.fn_add_edgelabel_hideshow()
        self.fn_end_script_tag()        
        self.fn_end_html_content()
        output_file_path = os.path.join(
            base_dir,
            'output',
            'graph',
            'jandroid.html'
        )
        with open(output_file_path, 'w') as f:
            f.write(self.html_content)
        logging.info('Custom graph can be found at ' + output_file_path)
    
    def fn_initialise_links(self, base_dir):
        """Processes .links files (to create explot chains).
        
        :param base_dir: string denoting path to base directory
        """
        template_folder = os.path.join(
            base_dir,
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
        
        for graph_link_file in graph_link_files:
            self.fn_process_individual_link_file(graph_link_file)
            
    def fn_process_individual_link_file(self, graph_link_file):
        """Processes an individual links file.
        
        The contents of the links file is added to an object.
        
        :param graph_link_file: string denoting path to link file
        """
        with open(graph_link_file, 'r') as link_file_input:
            try:
                link_file_object = json.load(link_file_input)
            except:
                link_file_object = None
        if link_file_object == None:
            return
            
        for from_bug in link_file_object:
            if from_bug not in self.links:
                self.links[from_bug] = []
            to_bugs = link_file_object[from_bug]
            if type(to_bugs) is str:
                to_bugs = [to_bugs]
            for to_bug in to_bugs:
                if to_bug not in self.links[from_bug]:
                    self.links[from_bug].append(to_bug)
    
    def fn_get_node_identifier(self, base_dir):
        """Reads in the node identifier from config file.
        
        The node identifier is assigned to an attribute.
        
        :param base_dir: string denoting path to base directory
        """
        config = configparser.ConfigParser()
        config_file_path = os.path.join(
            base_dir,
            'config',
            'jandroid.conf'
        )
        config.read(config_file_path)
        if config.has_section('NEO4J'):
            if config.has_option('NEO4J', 'NODE_IDENTIFIER'):
                self.node_identifier = (
                    config['NEO4J']['NODE_IDENTIFIER']
                )            
    
    def fn_enumerate_bugs(self, analysis_output):
        """Add all bug names from analysis output to an object.
        
        :param analysis_output: dictionary object containing the output of 
            the Jandroid analysis
        """
        bugs = set()
        for individual_app in analysis_output:
            bugs_present = self.fn_identify_bug_presence(
                analysis_output[individual_app]
            )
            for bug in bugs_present:
                bugs.add(bug)
        self.bugs = list(bugs)
        
    def fn_process_analysis_object(self, analysis_output):
        """Calls functions to process different parts of the analysis output.
        
        :param analysis_output: dictionary object containing the output of 
            the Jandroid analysis
        """
        # First add one node for each app that satisfies at least one bug.
        # These are used to show a compact view of the system.
        self.fn_add_basic_nodes(analysis_output)
        # Add edges for the above basic nodes.
        self.fn_add_basic_edges()
        
        # Add the nodes+edges that are generated as output by Jandroid.
        # When you double-click a basic node, it should "expand" and display
        #  the complex nodes corresponding to the same app.
        self.fn_add_complex_nodes_edges(analysis_output)
        # Create links between basic nodes and complex nodes. That is, we need
        #  links for when one node is expanded and another is compact.
        self.fn_add_basic_to_trace_edges()
    
    def fn_add_basic_nodes(self, analysis_output):
        """Adds nodes corresponding to apps that satisfy at least one bug.
        
        :param analysis_output: dictionary object containing the output of 
            the Jandroid analysis
        """
        # First get a count of all apps that satisfy at least one bug.
        app_counter = 0
        for individual_app in analysis_output:
            bugs_present = self.fn_identify_bug_presence(
                analysis_output[individual_app]
            )
            # If there are no bugs satisfied, then don't display this node.
            # This reduces clutter.
            if bugs_present == []:
                continue
            app_counter += 1
        
        format_string = '{0:0=d}'
        if app_counter > 9:
            format_string = '{0:0=2d}'
        if app_counter > 99:
            format_string = '{0:0=3d}'
            
        # Reset counter.
        app_counter = 0
        # Now create nodes. Do this per-app.
        for individual_app in analysis_output:
            bugs_present = self.fn_identify_bug_presence(
                analysis_output[individual_app]
            )
            # If there are no bugs satisfied, then don't display this node.
            # This reduces clutter.
            if bugs_present == []:
                continue

            # If this app has already been added, skip.
            if individual_app in self.existing_node_ids:
                continue

            # Give the nodes some short display name (like "App0", "App1").
            # The actual names are too long to be displayed properly.
            self.app_ids[individual_app] = 'App' + format_string.format(app_counter)
            
            # Create a node object in vis.js style.
            node_object = {
                'id': individual_app,
                'package': individual_app,
                'title': individual_app,
                'label': self.app_ids[individual_app],
                'bugs': bugs_present,
                'type': 'basic'
            }
            self.nodes.append(node_object)
            
            # Increment app_counter (to use as node display IDs).
            app_counter += 1
            
            # Add to a list to prevent analysing again.
            self.existing_node_ids.append(individual_app)
            
    def fn_identify_bug_presence(self, output_object):
        """Identifies all bugs that an app satisfies.
        
        :param output_object: dictionary object corresponding to the app
        :returns: list of bugs satisfied by the app
        """
        bugs = set()
        bug_obj = output_object['bug_obj']
        for bug_element in bug_obj:
            if bug_obj[bug_element] == True:
                bugs.add(bug_element)
        return list(bugs)
    
    def fn_add_basic_edges(self):
        """Adds EXPLOITS edges based on links files."""
        for from_bug_raw in self.links:
            if from_bug_raw.endswith('Start'):
                from_bug = from_bug_raw[:-5]
            if from_bug_raw.endswith('End'):
                from_bug = from_bug_raw[:-3]
            else:
                from_bug = from_bug_raw
            from_node_ids = self.fn_get_basic_nodeid_from_bug(from_bug)
            for to_bug_raw in self.links[from_bug_raw]:
                if to_bug_raw.endswith('Start'):
                    to_bug = to_bug_raw[:-5]
                if to_bug_raw.endswith('End'):
                    to_bug = to_bug_raw[:-3]
                else:
                    to_bug = to_bug_raw
                to_node_ids = self.fn_get_basic_nodeid_from_bug(to_bug)
                for from_node_id in from_node_ids:
                    for to_node_id in to_node_ids:
                        self.edges.append({
                            'id': 'edge'+str(self.edge_counter),
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'EXPLOITS',
                            '_label': 'EXPLOITS'
                        })
                        self.edge_counter += 1
                
    def fn_get_basic_nodeid_from_bug(self, bug_name):
        """Gets IDs for all nodes that satisfy a particular bug.
        
        :param bug_name: string name for bug
        :returns: list of node IDs for apps that satisfied the given bug
        """
        output_ids = []
        for node in self.nodes:
            for node_bug in node['bugs']:
                if bug_name == node_bug:
                    output_ids.append(node['id'])
        return output_ids
    
    def fn_add_complex_nodes_edges(self, analysis_output):
        """Creates nodes and edges based on actual Jandroid graph output.
        
        :param analysis_output: dictionary object containing the output of 
            the Jandroid analysis
        """
        for individual_app in analysis_output:
            # Get nodes with combined attributes and labels.
            combined_nodes = \
                self.inst_graph_helper_main.fn_get_graphable_nodes(
                    analysis_output[individual_app]['graph_list']
                )
            # Get relationships with combined attributes and labels.
            combined_rels = \
                self.inst_graph_helper_main.fn_get_graphable_relationships(
                    analysis_output[individual_app]['graph_list']
                )
            # Add nodes and edges for the app.
            self.fn_add_complex_nodes_edges_for_individual_app(
                individual_app,
                combined_nodes,
                combined_rels
            )        
            
    def fn_add_complex_nodes_edges_for_individual_app(self, app, nodes, rels):
        """Calls functions to add complex nodes and edges for an app.
        
        :param app: string denoting app name
        :param nodes: list of node objects
        :param rels: list of relationship objects
        """
        self.fn_add_nodes_for_individual_app(app, nodes)
        self.fn_add_edges_for_individual_app(app, rels)
    
    def fn_add_nodes_for_individual_app(self, app, node_list):
        """Creates complex nodes for a particular app.
        
        :param app: string denoting app name
        :param node_list: list of node objects
        """
        for jandroid_output_node_obj in node_list:
            # Create node object.
            vis_node_object = {}
            vis_node_object['package'] = app
            # The label is what is displayed within the node.
            vis_node_object['label'] = self.app_ids[app]
            # This is a complex node.
            vis_node_object['type'] = 'complex'
            # List of bugs this app satisfies.
            vis_node_object['bugs'] = jandroid_output_node_obj['labels']
            # Hide on start. This node is only displayed if user double-clicks
            #  a basic node.
            vis_node_object['hidden'] = 'true'
            # Add all other attributes.
            attribute_obj = jandroid_output_node_obj['attributes']
            for attribute_name in attribute_obj:
                attribute_value = attribute_obj[attribute_name]
                if attribute_name == self.node_identifier:
                    if (attribute_value in 
                            self.existing_node_ids):
                        vis_node_object = {}
                        break
                    self.existing_node_ids.append(
                        attribute_value
                    )
                    vis_node_object['id'] = \
                        attribute_value
                    vis_node_object['title'] = \
                        attribute_value
                    if '|MAYBE|' in attribute_value:
                        vis_node_object['shapeProperties'] = {}
                        vis_node_object['shapeProperties']['borderDashes'] = [5,5]
                else:
                    vis_node_object[attribute_name] = \
                        attribute_value
            vis_node_object['borderWidth'] = 1
            vis_node_object['borderWidthSelected'] = 2
            if 'bugs' not in vis_node_object:
                continue
            for single_bug in vis_node_object['bugs']:
                if single_bug.endswith('Start'):
                    if vis_node_object['id'] not in self.start_node_ids:
                        self.start_node_ids.append(vis_node_object['id'])
                if single_bug.endswith('End'):
                    if vis_node_object['id'] not in self.end_node_ids:
                        self.end_node_ids.append(vis_node_object['id'])
                
            if vis_node_object == {}:
                continue
            # Add the node object to the list of node objects.
            self.nodes.append(vis_node_object)
        
    def fn_add_edges_for_individual_app(self, app, edge_list):
        """Adds CALLS edge to trace chains.
        
        :param app: string denoting app name
        :param edge_list: list of edge objects
        """
        for edge_object in edge_list:
            from_node_id = \
                edge_object['from']['attributes'][self.node_identifier]
            to_node_id = edge_object['to']['attributes'][self.node_identifier]
            self.edges.append({
                'id': 'edge'+str(self.edge_counter),
                'from': from_node_id,
                'to': to_node_id,
                'label': 'CALLS',
                '_label': 'CALLS'
            })
            self.edge_counter += 1
        
    def fn_add_basic_to_trace_edges(self):
        """Add EXPLOITS edges for complex nodes."""
        # Complex to complex.
        for from_bug in self.links:
            from_node_ids = self.fn_get_basic_nodeid_from_bug(from_bug)
            for to_bug in self.links[from_bug]:
                to_node_ids = self.fn_get_basic_nodeid_from_bug(to_bug)
                for from_node_id in from_node_ids:
                    for to_node_id in to_node_ids:
                        self.edges.append({
                            'id': 'edge'+str(self.edge_counter),
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'EXPLOITS',
                            '_label': 'EXPLOITS'
                        })
                        self.edge_counter += 1
                        
        # Basic to complex-with-trace
        for from_bug in self.links:
            from_node_ids = self.fn_get_basic_nodeid_from_bug(from_bug)
            for to_bug_raw in self.links[from_bug]:
                to_bug = to_bug_raw.replace('Start', '').replace('End', '')
                to_node_ids = self.fn_get_basic_nodeid_from_bug(to_bug)
                for from_node_id in from_node_ids:
                    for to_node_id in to_node_ids:
                        node_object = \
                            self.fn_get_node_object_from_id(to_node_id)
                        if node_object['type'] != 'basic':
                            continue
                        self.edges.append({
                            'id': 'edge'+str(self.edge_counter),
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'EXPLOITS',
                            '_label': 'EXPLOITS'
                        })
                        self.edge_counter += 1
                        
        # Complex-with-trace to basic.
        for from_bug_raw in self.links:
            from_bug = from_bug_raw.replace('Start', '').replace('End', '')
            from_node_ids = self.fn_get_basic_nodeid_from_bug(from_bug)
            for to_bug in self.links[from_bug_raw]:
                to_node_ids = self.fn_get_basic_nodeid_from_bug(to_bug)
                for from_node_id in from_node_ids:
                    node_object = \
                        self.fn_get_node_object_from_id(from_node_id)
                    if node_object['type'] != 'basic':
                        continue
                    for to_node_id in to_node_ids:
                        self.edges.append({
                            'id': 'edge'+str(self.edge_counter),
                            'from': from_node_id,
                            'to': to_node_id,
                            'label': 'EXPLOITS',
                            '_label': 'EXPLOITS'
                        })
                        self.edge_counter += 1
        
    def fn_get_node_object_from_id(self, node_id):
        """Returns node object based on ID.
        
        :param node_id: string identifier for node
        :returns: node object corresponding to the given ID
        """
        for node_obj in self.nodes:
            if node_obj['id'] == node_id:
                return node_obj

    def fn_begin_html_content(self):
        """Begins the HTML page content."""
        # Create filters for the nodes.
        # Filter by app.
        app_filter = '<select id="appfilter" size=8 multiple>' 
        all_apps = list(self.app_ids.keys())
        all_apps.sort(key=str.lower)
        for app in all_apps:
            app_filter = app_filter \
                         + '<option value="' \
                         + app \
                         + '">' \
                         + app \
                         + '</option>'
        app_filter = app_filter + '</select>'
        
        # Filter by bug.
        bug_filter = '<select id="bugfilter" size=8 multiple>'
        self.bugs.sort()
        for bug in self.bugs:
            bug_filter = bug_filter \
                         + '<option value="' \
                         + bug \
                         + '">' \
                         + bug \
                         + '</option>'
        bug_filter = bug_filter + '</select>'
        
        # Filter by view.
        type_filter = '<select id="typefilter">' \
                      + '<option value="basic">Compact View</option>' \
                      + '<option value="complex">Expanded View</option>' \
                      + '</select>'
                    
        # Actual HTML content.
        self.html_content = """
        <!doctype html>
        <html>
        <head>
            <title>Jandroid: Output</title>

            <script type="text/javascript" src="./js/vis-network.min.js"></script>
            <link href="./css/vis-network.min.css" rel="stylesheet" type="text/css"/>
            <link href="./css/jandroid.css" rel="stylesheet" type="text/css"/>
        </head>
        <body>

        <div id="uifilters"> 
        <b>Styling&nbsp;&nbsp;</b> 
        <select id="colourchoice">
            <option value="bybug">Colour by bug</option>
            <option value="byapp">Colour by app</option>
        </select>
        <select id="edgelabels">
            <option value="showedgelabels">Show edge labels</option>
            <option value="hideedgelabels">Hide edge labels</option>
        </select>
        
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
        
        <b>View&nbsp;&nbsp;</b> 

        """ + type_filter + """
        
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
        
        <b>Highlight&nbsp;&nbsp;</b> 
        <input type="checkbox" name="highlightstart" id="highlightstart" value="highlightstart"> Start nodes
        <input type="checkbox" name="highlightend" id="highlightend" value="highlightend"> End nodes
        
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
        <button id="redraw" class="tooltip">  Redraw  <span class="tooltiptext">Redraw the nodes</span></button>
        </div>
        
        <div id="maincontainer">
        <div id="jandroidnw"></div>
        <div id="mainfilters">
        <b>Filter by App</b><br />
        """ + app_filter + """
        <br /><br />
        <b>Filter by Bug</b><br />
        """ + bug_filter + """
        <br /><br />
        <button id="clearfilters">  Clear All Filters  </button>
        <br /><br /><br />
        <button id="applyfilters">  Apply Filters  </button>
        
        </div>
        </div>
        
        <p style="font-size:12px"><em>
            Output from running Jandroid. 
            Click on a node to get more details about it.
            Double-click on a node to expand.
            Double-click again to collapse.
        </em></p>
        <br />
        <pre id="eventSpan"></pre>

        <script type="text/javascript">
        """
    
    def fn_initialise_colours(self):
        num_colours = len(self.app_ids.keys())
        if len(self.bugs) > num_colours:
            num_colours = len(self.bugs)
        colour_palette = []
        r = lambda: random.randint(90,210)
        for i in range(num_colours):
            colour = '#{:02x}{:02x}{:02x}'.format(r(), r(), r())
            colour_palette.append(colour)
        # colour_palette = [
            # '#4A95C4', '#5e9660', '#705e96', '#bfcc4b', '#4bbfcc', '#bc51b1',
        # ]
        # while len(colour_palette) < len(self.app_ids.keys()):
            # colour_palette = colour_palette + colour_palette
        # while len(colour_palette) < len(self.bugs):
            # colour_palette = colour_palette + colour_palette
        random.shuffle(colour_palette)

        # Initialise per-app colour object.
        colour_by_app = {}
        app_counter = 0
        for app in self.app_ids:
            colour_by_app[app] = colour_palette[app_counter]
            app_counter +=1

        # Initialise per-bug colour object.
        colour_by_bug = {}
        app_counter = 0
        for bug in self.bugs:
            colour_by_bug[bug] = colour_palette[app_counter]
            app_counter +=1
        
        # Add this data to HTML (well, JS).
        self.html_content = self.html_content + """
            var colour_palette = """ + str(colour_palette) + """;
            var num_colours = colour_palette.length;
            var colour_by_app = """ + str(colour_by_app) + """;
            var colour_by_bug = """ + str(colour_by_bug) + """;
        """
    
    def fn_add_node_dataset(self):
        """Creates the vis nodes dataset."""
        self.html_content = self.html_content + """
            var nodes = new vis.DataSet(
        """
        self.html_content = self.html_content + str(self.nodes) + ');'
        
        self.html_content = self.html_content + """
            var startNodes = """ + str(self.start_node_ids) + ';'
            
        self.html_content = self.html_content + """
            var endNodes = """ + str(self.end_node_ids) + ';'
        
    def fn_add_edge_dataset(self):
        """Creates the vis edges dataset."""
        self.html_content = self.html_content + """
            var edges = new vis.DataSet(
        """
        self.html_content = self.html_content + str(self.edges) + ');'  
        
    def fn_create_network(self):
        """Configures network parameters and creates new vis network."""
        self.html_content = self.html_content + """
        // create a network
        var container = document.getElementById('jandroidnw');
        var data = {
            nodes: nodes,
            edges: edges
        };

        var options = {
			interaction:{
                hover: true,
                hideEdgesOnZoom: true,
                navigationButtons: true,
                dragView: false,
                zoomView: false
            },
			manipulation: {
				enabled: false
			},
            nodes: {
              shape: 'circle'
            },
            edges: {
                physics: false,
                arrows: {
                    to:     {enabled: true, scaleFactor:1, type:'arrow'},
                    middle: {enabled: false, scaleFactor:1, type:'arrow'},
                    from:   {enabled: false, scaleFactor:1, type:'arrow'}
                },
                font: {
                    align: 'middle'
                },
                smooth: false
            }
		};

        var network = new vis.Network(container, data, options);
        """

    def fn_add_onclick_script(self):
        """Adds a function to display node attributes when clicked."""
        self.html_content = self.html_content + """
        network.on("click", function (params) {
            var ids = params.nodes;
            var clickedNodes = nodes.get(ids);
            var clickedNode = clickedNodes[0];
            var string = "<b>package: </b>" + clickedNode["package"] + "   " + "<b>title: </b>" + clickedNode["title"] + "   " + "<b>bugs: </b>" + clickedNode["bugs"];  
            for (key in clickedNode) {
                if ((key == "id")  || (key == "label") || (key == "_label") || (key == "hidden") || (key == "type") || (key == "color") || (key == "shapeProperties") || (key == "borderWidth")|| (key == "package")|| (key == "title") || (key == "bugs") || (key == "borderWidthSelected")) {
                    continue
                }
                if (string == '') {
                    string = string + "<b>" + key + ": </b>" + clickedNode[key];
                } else {
                    string = string + "   " + "<b>" + key + ": </b>" + clickedNode[key];
                }  
            }
            document.getElementById('eventSpan').innerHTML = string;
        });
        
        """
    
    def fn_add_ondoubleclick_script(self):
        """Adds a function to expand/collapse nodes on double-click."""
        self.html_content = self.html_content + """
        network.on("doubleClick", function (params) {
            var ids = params.nodes;
            var clickedNodes = nodes.get(ids);
            var clickedNode = clickedNodes[0];
            var clickedNodeId = clickedNode["id"];
            var clickedNodeType = clickedNode["type"];
            var clickedAppPackage = clickedNode["package"];
            var bugFilterOptions = document.getElementById("bugfilter").options;
            var selectedBugs = [];
            var useBugSelector = true;
            for (i=0; i<bugFilterOptions.length; i++) {
                if (bugFilterOptions[i].selected) {selectedBugs.push(bugFilterOptions[i].value);}
            }
            toggleIdsForSameKey("package", clickedAppPackage, selectedBugs);
        });
        
        function getAllIdsForSameKey (keyName, keyValue) {
            var nodeIds = [];
            var nodeData = nodes["_data"];
            for (node in nodeData) {
                if (nodeData[node][keyName] == keyValue) {
                    nodeIds.push(nodeData[node]["id"])
                }
                
            }
            return nodeIds;
        }
        
        function toggleIdsForSameKey (keyName, keyValue, selectedBugs) {
            var nodeData = nodes["_data"];
            for (node in nodeData) {
                if (nodeData[node][keyName] == keyValue) {
                    var currentHiddenState = nodeData[node]["hidden"];
                    if (currentHiddenState == undefined) {
                        currentHiddenState = false
                    }
                    if (currentHiddenState == false) {
                        nodes.update([
                            {
                                "id": nodeData[node]["id"],
                                "hidden": true
                            }
                        ]);
                        continue;
                    }
                    var showNodeBasedOnBug = false;
                    if (selectedBugs == []) {
                        showNodeBasedOnBug = true;
                    } else {
                        showNodeBasedOnBug = false;
                        var node_bugs = nodeData[node]['bugs'];
                        var numBugsSatisfied = 0;
                        for (x=0; x<selectedBugs.length; x++) {
                            selectedBug = selectedBugs[x];
                            if (nodeData[node]["bugs"].indexOf(selectedBug) >= 0) {
                                numBugsSatisfied = numBugsSatisfied + 1
                            }
                        }
                        if (numBugsSatisfied == selectedBugs.length) {
                            showNodeBasedOnBug = true;
                        }
                    }
                    if (showNodeBasedOnBug == true) {
                        nodes.update([
                            {
                                "id": nodeData[node]["id"],
                                "hidden": false
                            }
                        ]);
                    }
                }
            }
            network.fit();
        }
        
        """
    
    def fn_add_redraw(self):
        """Adds a function to redraw network."""
        self.html_content = self.html_content + """
        document.getElementById("redraw").onclick = function() {redrawNetwork()};
        function redrawNetwork() {
            var mathRandom = Math.floor(Math.random() * 10);
            options['layout'] = {'randomSeed':mathRandom};
            try {
                network.setOptions(options);
            } catch (err){
                alert(err.message);
            }
            
            network.setData({nodes: nodes, edges: edges});
            network.fit();
        }
        """
    
    def fn_add_select_node(self):
        """Adds a function to highlight nodes."""
        self.html_content = self.html_content + """
        document.getElementById("appfilter").onchange = function() {highlightNodesBasedOnApp()};
        function highlightNodesBasedOnApp() {
            var appFilterOptions = document.getElementById("appfilter").options;
            var selectedApps = [];
            for (i=0; i<appFilterOptions.length; i++) {
                if (appFilterOptions[i].selected) {selectedApps.push(appFilterOptions[i].value);}
            }
            if (selectedApps == []) {
                network.unselectAll();
            } else {
                network.selectNodes(selectedApps);
            }
        }
        """
        
    def fn_add_nodefilter(self):
        """Adds all the filter change functions.
        
        This is essentially just selectively hiding/showing nodes.
        """
        self.html_content = self.html_content + """
        document.getElementById("applyfilters").onclick = function() {nodeFilterFunction()};
        document.getElementById("typefilter").onchange = function() {nodeFilterFunction()};

        function nodeFilterFunction() {
            var appFilterOptions = document.getElementById("appfilter").options;
            var selectedApps = [];
            var useAppSelector = true;
            for (i=0; i<appFilterOptions.length; i++) {
                if (appFilterOptions[i].selected) {selectedApps.push(appFilterOptions[i].value);}
            }
            if (selectedApps.length == 0) {useAppSelector = false;}
            
            var bugFilterOptions = document.getElementById("bugfilter").options;
            var selectedBugs = [];
            var useBugSelector = true;
            for (i=0; i<bugFilterOptions.length; i++) {
                if (bugFilterOptions[i].selected) {selectedBugs.push(bugFilterOptions[i].value);}
            }
            if (selectedBugs.length == 0) {useBugSelector = false;}
            
            var selectedType = document.getElementById("typefilter").value;
            
            var nodeData = nodes["_data"];
            for (node in nodeData) {
                var showNodeBasedOnBug = false;
                if (useBugSelector == false) {
                    showNodeBasedOnBug = true;
                } else {
                    numBugsSatisfied = 0
                    for (x=0; x<selectedBugs.length; x++) {
                        selectedBug = selectedBugs[x];
                        if (nodeData[node]["bugs"].indexOf(selectedBug) >= 0) {
                            numBugsSatisfied = numBugsSatisfied + 1
                        }
                    }
                    if (numBugsSatisfied == selectedBugs.length) {
                        showNodeBasedOnBug = true;
                    }
                }
                
                var showNodeBasedOnApp = false;
                if (useAppSelector == false) {
                    showNodeBasedOnApp = true;
                } else {
                    if (selectedApps.indexOf(nodeData[node]["package"]) >= 0) {
                        showNodeBasedOnApp = true;
                    }
                }

                var showNodeBasedOnType = false;
                if (nodeData[node]["type"] == selectedType) {
                    showNodeBasedOnType = true
                }
                if ((showNodeBasedOnApp == true) && (showNodeBasedOnBug == true) && (showNodeBasedOnType == true)) {
                    nodes.update([
                        {
                            "id": nodeData[node]["id"],
                            "hidden": false
                        }
                    ]);
                } else {
                    nodes.update([
                        {
                            "id": nodeData[node]["id"],
                            "hidden": true
                        }
                    ]);
                }
            }
            network.fit();
        }
        
        """
    
    def fn_add_clearfilters(self):
        """Clears the multi-select filters.
        """
        self.html_content = self.html_content + """
        document.getElementById("clearfilters").onclick = function() {clearFilterFunction()};
        function clearFilterFunction() {
            var appFilterOptions = document.getElementById("appfilter").options;
            for (i=0; i<appFilterOptions.length; i++) {
                appFilterOptions[i].selected = false;
            }
            var bugFilterOptions = document.getElementById("bugfilter").options;
            for (i=0; i<bugFilterOptions.length; i++) {
                bugFilterOptions[i].selected = false;
            }
            
            nodeFilterFunction();
        }
        """
    
    def fn_add_highlightstart(self):
        """Highlights (or removes highlight from) Start nodes."""
        self.html_content = self.html_content + """
        document.getElementById("highlightstart").onchange = function() {highlightStartFunction()};
        function highlightStartFunction() {
            var shouldHighlightStart = document.getElementById("highlightstart").checked;
            var borderRadius = 1;
            if (shouldHighlightStart == true) {borderRadius = 5;}
            for (i=0; i<startNodes.length; i++) {
                nodeId = startNodes[i];
                nodes.update([
                    {
                        "id": nodeId,
                        "borderWidth": borderRadius
                    }
                ]);
            }    
        }
        """
        
    def fn_add_highlightend(self):
        """Highlights (or removes highlight from) End nodes."""
        self.html_content = self.html_content + """
        document.getElementById("highlightend").onchange = function() {highlightEndFunction()};
        function highlightEndFunction() {
            var shouldHighlightEnd = document.getElementById("highlightend").checked;
            var borderWidth = 1;
            var borderWidthSelected = 2;
            if (shouldHighlightEnd == true) {
                borderWidth = 5;
                borderWidthSelected = 5;
            }
            for (i=0; i<endNodes.length; i++) {
                nodeId = endNodes[i];
                nodes.update([
                    {
                        "id": nodeId,
                        "borderWidth": borderWidth,
                        "borderWidthSelected": borderWidthSelected
                    }
                ]);
            }    
        }
        """
        
    def fn_add_node_colourer(self):
        """Adds a function to change node colours based on app or bug name."""
        self.html_content = self.html_content + """
        document.getElementById("colourchoice").onchange = function() {nodeColourFunction()};
        function nodeColourFunction() {
            var selectedColourMode = document.getElementById("colourchoice").value;
            if (selectedColourMode == "byapp") {
                nodeColourByApp();
            } else {
                nodeColourByBug()
            }
        }
        nodeColourFunction();
        
        function nodeColourByApp() {
            var app_name;
            var nodeData = nodes["_data"];
            for (node in nodeData) {
                app_name = nodeData[node]["package"];
                node_colour = colour_by_app[app_name];
                nodes.update([
                    {
                        "id": nodeData[node]["id"],
                        "color": node_colour
                    }
                ]);
            }
        }
        
        function nodeColourByBug() {
            var app_name;
            var nodeData = nodes["_data"];
            for (node in nodeData) {
                for (bug in colour_by_bug) {
                    node_colour = colour_by_bug[bug]
                    if (nodeData[node]["bugs"].indexOf(bug) >= 0) {
                        nodes.update([
                            {
                                "id": nodeData[node]["id"],
                                "color": node_colour
                            }
                        ]);
                    }
                }
            }
        }
        """
    
    def fn_add_edgelabel_hideshow(self):
        """Adds a function to hide/show edge labels based on user selection."""
        self.html_content = self.html_content + """
        document.getElementById("edgelabels").onchange = function() {edgeLabelFunction()};
        function edgeLabelFunction() {
            var labelDisplay = document.getElementById("edgelabels").value;
            var edgeData = edges["_data"];
            if (labelDisplay == "showedgelabels") {
                for (edge in edgeData) {
                    edges.update([
                        {
                            "id": edgeData[edge]["id"],
                            "label": edgeData[edge]["_label"]
                        }
                    ]);
                }
            } else {
                for (edge in edgeData) {
                    edges.update([
                        {
                            "id": edgeData[edge]["id"],
                            "label": " "
                        }
                    ]);
                }
            }
        }
        """
        
    def fn_end_script_tag(self):
        """Ends the script part."""
        self.html_content = self.html_content \
                            + """
        </script>"""

    def fn_end_html_content(self):
        """Ends the HTML file."""
        self.html_content = self.html_content + """
        </body>
        </html>
        """