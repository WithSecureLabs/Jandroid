import logging
from requirements_checker import RequirementsChecker
from common import *


class PluginMain:
    def __init__(self, base_dir, script_dir, app_dir):
        """Sets script paths.
        
        :param base_dir: string specifying path to the base/root directory 
            (contains src/, templates/, etc)
        :param script_dir: string specifying path to the main script 
            directory, i.e., <root>/src/
        :param app_dir: string specifying path to the directory containing the 
            applications under analysis
        """
        self.path_base_dir = base_dir
        self.path_script_dir = script_dir
        self.path_app_folder = app_dir
        
    def fn_start_plugin_analysis(self, bool_gen_graph=True, graph_type=None,
                                 bug_object=None, bool_pull_apps=False, 
                                 app_pull_src='device'):
        """Starts the main Android-specific analysis.
        
        :param bool_gen_graph: boolean specifying whether graphing is required
        :param bug_object: dictionary object containing all bug templates
        :param bool_pull_apps: boolean specifying whether apps should be 
            extracted (from device or file) before analysis is performed
        :param app_pull_src: if apps *are* to be extracted, then the location 
            from which they are to be extracted ("device", "ext4", or "img")
        """
        logging.info('Initiating Android analysis.')
        
        # Set parameters.
        self.bool_generate_graph = bool_gen_graph
        self.graph_type = graph_type
        self.master_bug_object = bug_object
        self.bool_pull_apps = bool_pull_apps
        self.pull_source = app_pull_src
        
        # First perform required checks.
        # Initialise the requirements checker class.
        inst_req_check = RequirementsChecker(
            self.path_base_dir,
            self.path_app_folder
        )
        # Perform the checks.
        self.path_platform_tools = inst_req_check.fn_perform_initial_checks(
            bool_pull_apps,
            app_pull_src
        )
        
        # Extract apps, if required.
        if self.bool_pull_apps == True:
            self.fn_extract_apps()

        # FINALLY, start the actual analysis.
        self.fn_start_analysis()

    def fn_extract_apps(self):
        """Instantiate class to extract apps."""
        from app_extractor import AppExtractor

        inst_app_extractor = AppExtractor(
            self.path_base_dir,
            self.path_app_folder,
            self.path_platform_tools,
            self.pull_source
        )
        inst_app_extractor.fn_extract_apps()

    def fn_start_analysis(self):
        """Instantiate and call the main analysis function."""
        from app_analyser import AnalyseApps

        inst_app_analyser = AnalyseApps(
            self.path_base_dir,
            self.path_script_dir,
            self.path_app_folder,
            self.master_bug_object,
            self.bool_generate_graph,
            self.graph_type
        )
        inst_app_analyser.fn_analyse_apps()