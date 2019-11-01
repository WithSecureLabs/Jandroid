import os
import sys
import logging
import argparse
import platform
import configparser
from common import JandroidException
from template_parser import TemplateParser


class Jandroid:
    """Tool for analysing and template-matching of applications."""
    
    def __init__(self, path_app_folder=None, bool_generate_graph=None,
                 analysis_platform=None, pull_source=None):
        """Performs preliminary checks and initialises variables."""
        # Banner.
        print('\n----------------------------\n'
              '           JANDROID'
              '\n----------------------------\n')

        # We require Python > v3.4
        if sys.version_info < (3, 4):
            print(
                'Sorry, this script doesn\'t work with '
                + 'Python versions lower than v3.4.'
            )
            sys.exit(1)

        # Set initial logging config.
        logging.basicConfig(
            stream=sys.stdout,
            format='%(levelname)-8s %(message)s',
            level=logging.INFO
        )

        # Working directory will be the current directory.
        self.path_script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Set argument defaults.
        self.bool_pull_apps = False
        self.pull_source = 'd'
        self.bool_generate_graph = False
        self.graph_type = 'neo4j'
        self.analysis_platform = 'android'
        
        # Set values from function arguments.
        if path_app_folder != None:
            self.path_app_folder = path_app_folder
        if bool_generate_graph != None:
            self.bool_generate_graph = bool_generate_graph
        if pull_source != None:
            self.pull_source = pull_source

        # Also check passed args.
        self.argparser = None
        # Set accepted args.
        self.__fn_set_args()
        # Check user-supplied arguments.
        self.__fn_check_args()
        
        # Sets all other paths.
        self.__fn_set_paths()
        
        # If app folder was not set by cmdline args or function arguments,
        #  we need to set it.
        if not hasattr(self, 'path_app_folder'):
            # Path to app files.
            self.path_app_folder = os.path.normpath(
                os.path.join(
                    self.path_base_dir,
                    'apps'
                )
            )

    def __fn_set_args(self):
        """Sets accepted arguments for the tool.
        
        Jandroid accepts a number of input arguments/flag.
        These include setting the application folder, the platform of 
        interest), whether apps should be pulled from a device/image, 
        and whether graphing is required.
        """
        self.argparser = argparse.ArgumentParser(
            description = 'A tool for performing pattern matching against '
                          + 'applications.',
            epilog = 'Note that this tool has only been '
                     + 'tested with Python 3.7+. '
                     + 'Will NOT work with versions less than 3.4.\n'
        )
        self.argparser.add_argument(
            '-f',
            '--folder',
            type = str,
            action = 'store',
            help = 'folder containing apps to be analysed '
                   + '(or to which apps should be pulled, '
                   + 'when used with the -p flag). '
                   + 'Provide absolute path to folder as argument.'
        )
        self.argparser.add_argument(
            '-p',
            '--platform',
            choices = ['android'],
            action = 'store',
            nargs = '?',
            const = self.pull_source,
            help = 'the type of files/platform to be analysed, '
                   + 'e.g., android. Only android is currently '
                   + 'supported. Support for other files to be added.'
        )
        self.argparser.add_argument(
            '-e',
            '--extract',
            choices = ['device', 'ext4', 'img'],
            action = 'store',
            nargs = '?',
            const = self.pull_source,
            help = 'extract Android apps from connected device '
                   + 'or system image. '
                   + 'Only relevant when platform=android. '
                   + 'Use "-e device" to pull APKs from device (default). '
                   + '(Make sure that only one Android device '
                   + 'is connected and that it is unlocked.) '
                   + 'Use "-e ext4" to extract applications '
                   + 'from an ext4 system image. '
                   + 'Use "-e img" to pull applications from '
                   + 'a .img system image. '
                   + 'Apps get pulled to <root>/apps/ directory '
                   + 'or to folder specified with the -f option. '
                   + 'If pulling from system image, the image '
                   + 'must be in this folder as well.'
        )
        self.argparser.add_argument(
            '-g',
            '--graph',
            choices = ['neo4j', 'visjs', 'both'],
            action = 'store',
            nargs = '?',
            const = self.graph_type,
            help = 'show results on graph. '
                   + 'Use "-g neo4j" to output to a Neo4j database. '
                   + 'Requires that a Neo4j database be up and '
                   + 'running on http://localhost:7474 '
                   + 'with username:neo4j and password:n3o4j '
                   + '(or user-specified values from config). '
                   + 'Or use "-g visjs" to create a vis.js network in html '
                   + 'that can be viewed from the output folder. '
                   + 'Or use "-g both" to generate both.'
        )

    def fn_main(self, gui=False):
        """Starts the various test and analysis processes.
        
        This function doesn't do very much on its own.
        It instantiates a number of other classes and performs checks
        and achieves functionality via methods within those classes.
        """
        # Set log level according to value in configuration file.
        self.__fn_set_log_level()
        
        # If graphing is required, then check connection
        #  to graph.
        if self.bool_generate_graph == True:
            if ((self.graph_type == 'neo4j') or (self.graph_type == 'both')):
                self.__fn_test_graph_handler()

        # Check for templates.
        #  If they don't exist, there's nothing to check.
        if [f for f in os.listdir(self.path_to_templates)
                if (f.endswith('.template')
                and not f.startswith('.'))] == []:
            logging.critical(
                'Template directory contains no JSON templates. '
                + 'Exiting...'
            )
            sys.exit(1)
        # Create a master template from the individual
        #  templates.
        self.__fn_create_master_template()

        # Call the relevant plugin.
        # We need to add a new path to sys.path for the plugin.
        module_path = os.path.join(
            self.path_script_dir,
            'plugins',
            self.analysis_platform
        )
        sys.path.append(os.path.abspath(module_path))
        # Import the plugin.
        # Note that the plugin/<platform> folder *must* have a file
        #  named main.py within it.
        try:
            from main import PluginMain
        except Exception as e:
            logging.critical(
                'Unable to import plugin for '
                + self.analysis_platform
                + '.'
            )
            sys.exit(1)
        # Instantiate the plugin.
        # Note that the plugin class name (within main.py)
        #  *must* be the same for all plugins.
        try:
            inst_plugin_main = PluginMain(
                self.path_base_dir,
                self.path_script_dir,
                self.path_app_folder
            )
        except Exception as e:
            logging.critical(
                'Unable to instantiate plugin for '
                + self.analysis_platform
                + '.'
            )
            sys.exit(1)
        # Call the initial analysis function.
        # Note that PluginMain *must* have a function named
        #  fn_start_plugin_analysis taking 4 arguments.
        #try:
        inst_plugin_main.fn_start_plugin_analysis(
            self.bool_generate_graph,
            self.graph_type,
            self.master_template_object,
            self.bool_pull_apps,
            self.pull_source
        )
        # except JandroidException as e:
            # logging.critical(
                # '['
                # + e.args[0]['type']
                # + '] '
                # + e.args[0]['reason']
            # )
            # sys.exit(1)
        # except Exception as e:
            # if 'Interrupted function call' in str(e):
                # logging.warning(
                    # 'Interrupted function call. '
                    # + 'Presumably you killed the process? '
                    # + 'If not, something strange is going on.'
                # )
                # sys.exit(0)
            # else:
                # logging.critical(
                    # 'Error encountered during program execution: '
                    # + str(e)
                # )
                # sys.exit(1)
            
        # All done. Print end message.
        logging.info('All done.')

    def __fn_set_paths(self):
        # Set parent directory. Do this AFTER argparse, in case the
        #  script directory has been changed from GUI.
        #  This will be the base directory used for all other files.
        self.path_base_dir = os.path.normpath(
            os.path.join(
                self.path_script_dir,
                '../'
            )
        )
        
        # Set all other paths (some may get populated only later).
        # Path to config file.
        self.path_config_file = os.path.join(
            self.path_base_dir,
            'config',
            'jandroid.conf'
        )        
        # Path to templates.
        self.path_to_templates = os.path.join(
            self.path_base_dir,
            'templates',
            self.analysis_platform
        )

    def __fn_set_log_level(self):
        """Sets the level for logging based on config file."""
        # Define possible log levels.
        LEVELS = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }

        # Get current log level.
        current_log_level = logging.getLevelName(
            logging.getLogger().getEffectiveLevel()
        )
        log_level = current_log_level

        # Get desired log level from config file.
        config = configparser.ConfigParser()
        try:
            config.read(self.path_config_file)
        except Exception as e:
            logging.critical(
                'Error reading config file: '
                + str(e)
            )
            sys.exit(1)
        if config.has_section('LOGGING'):
            if config.has_option('LOGGING', 'LOG_LEVEL'):
                log_level = (
                    config['LOGGING']['LOG_LEVEL']
                )

        # Check whether desired log level is an accepted value.
        # If yes, set the log level.
        # Else, ignore and keep existing level.
        if (log_level.lower() not in LEVELS.keys()):
            logging.warning(
                'Invalid value in config file for LOG_LEVEL. '
                + 'Ignoring and using existing level: '
                + current_log_level
            )
        else:
            logging.getLogger().setLevel(LEVELS[log_level.lower()])

    def __fn_check_args(self):
        """Checks user arguments and sets relevant variables."""
        logging.debug('Checking user-supplied arguments.')
        args = self.argparser.parse_args()
        logging.debug('Arguments: ' + str(args))

        # If an app folder is specified, then use that instead of the default.
        if args.folder:
            self.path_app_folder = args.folder

        # Set the analysis "platform", i.e., the analysis target.
        if args.platform:
            self.analysis_platform = args.platform

        # Check if apps are to be pulled from a device/image.
        # (Relevant for Android analysis. Additional options
        #  may need to be added for other analyses.)
        if args.extract:
            self.pull_source = args.extract
            self.bool_pull_apps = True

        # Check if a graph is to be generated.
        if args.graph:
            self.bool_generate_graph = True
            self.graph_type = args.graph

    def __fn_test_graph_handler(self):
        """Tests connection to neo4j graph."""        
        # Instantiate graph handler.
        from neo4j_graph_handler import Neo4jGraphHandler
        inst_graph_handler = Neo4jGraphHandler(self.path_base_dir)
        try:
            inst_graph_handler.fn_connect_to_graph()
        except JandroidException as e:
            logging.critical(
                '['
                + e.args[0]['type']
                + '] '
                + e.args[0]['reason']
            )
            sys.exit(1)
        # We will be using a different connection later,
        #  so remove this connection.
        inst_graph_handler = None

    def __fn_create_master_template(self):
        """Generates 'master template object'.
        
        Jandroid works on pattern matching against templates.
        This function calls the TemplateParser, which will parse
        all templates (relevant to the current plugin) and returns
        a "master object".
        """
        # Instantiate template parser.
        inst_template_parser = TemplateParser(
            self.path_base_dir,
            self.analysis_platform
        )
        try:
            self.master_template_object = \
                inst_template_parser.fn_create_master_template_object()
        except JandroidException as e:
                logging.critical(
                    '['
                    + e.args[0]['type']
                    + '] '
                    + e.args[0]['reason']
                )
                sys.exit(1)
        inst_template_parser = None

        # An empty template means nothing to check.
        if ((self.master_template_object == None) or
                (self.master_template_object == {})):
            logging.critical(
                'No template object or empty template object. '
                + 'Check templates and retry.'
            )
            sys.exit(1)

# Instantiate and start Jandroid.
if __name__ == '__main__':
    inst_jandroid = Jandroid()
    inst_jandroid.fn_main()