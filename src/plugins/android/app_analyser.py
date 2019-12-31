import os
import gc
import sys
import json
import timeit
import signal
import fnmatch
import logging
import configparser
from multiprocessing import Process, JoinableQueue, active_children
from androguard.misc import *
from androguard.core import *
from manifest_analyser import ManifestAnalyser
from code_analyser import CodeAnalyser
from graph_helper_main import GraphHelperMain
from graph_helper_worker import GraphHelperWorker
from custom_grapher import CustomGrapher
from common import *

supported_filetypes = ['*.apk', '*.dex']
RESULT_KEY_BUG_OBJ = 'bug_obj'
RESULT_KEY_GRAPHABLES = 'graph_list'

class AnalyseApps():
    """The "parent" app analysis class.
    
    Note that this class doesn't perform the actual analysis. For that, 
    it creates worker threads that are instances of a different class.
    """
    
    def __init__(self, base_dir, script_dir, app_dir,
                 bug_obj, bool_gen_graph, graph_type):
        """Sets paths, reads configurations and initialises variables.
        
        :param base_dir: string specifying location of script base directory
        :param script_dir: string specifying location of script directory
        :param app_dir: string specifying path to directory containing 
            applications to be analysed
        :param bug_obj: the "master bug object" (dictionary)
        :param bool_gen_graph: boolean value indicating whether or not a graph 
            should be generated
        :param graph_type: string specifying whether the graph is neo4j or vis 
            or both
        """
        # Set paths.
        self.path_base_dir = base_dir
        self.path_script_dir = script_dir
        self.path_app_folder = app_dir
        
        # Get main bug object (as JSON/dict).
        self.master_bug_object = bug_obj
        
        # Initialise main output object.
        self.master_output_object = {}

        # If we need to generate graph, instantiate Graph Helper.
        self.bool_generate_graph = bool_gen_graph
        self.graph_type = graph_type
        if self.bool_generate_graph == True:
            self.inst_graph_helper_main = GraphHelperMain(self.path_base_dir)
            if self.graph_type in ['neo4j', 'both']:                
                self.inst_graph_helper_main.fn_initialise_neo4j()
            if self.graph_type in ['visjs', 'both']:
                self.inst_custom_grapher = CustomGrapher()

        # Get required number of worker threads from config file.
        self.num_analysis_instances = 1
        self.path_config_file = os.path.join(
            self.path_base_dir,
            'config',
            'jandroid.conf'
        )
        config = configparser.ConfigParser()
        config.read(self.path_config_file)
        if config.has_section('ANALYSIS'):
            if config.has_option('ANALYSIS',
                    'NUM_ANALYSIS_INSTANCES'):
                self.num_analysis_instances = int(
                    config['ANALYSIS']['NUM_ANALYSIS_INSTANCES']
                )
        config = None
        
        # Handle terminate events.
        signal.signal(signal.SIGINT, self.fn_exit_gracefully)
        signal.signal(signal.SIGTERM, self.fn_exit_gracefully)

    def fn_analyse_apps(self):
        """Instantiates worker threads for app analysis and handles job queues.
        
        This function enumerates the applications that are to be analysed, 
        creates job queues, initialises worker threads to perform the actual 
        application analysis, retrieves the results and invokes graphing 
        functions, if needed.
        """
        logging.info('Beginning analysis...')

        # Set up log levels for worker process.
        LEVELS = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }

        # Check to make sure app folder actually has .apk or .dex files.
        apps_to_analyse = []
        for root, _, filenames in os.walk(self.path_app_folder):
            for supported_filetype in supported_filetypes:
                for filename in fnmatch.filter(filenames, supported_filetype):
                    apps_to_analyse.append(os.path.join(root, filename))
        if apps_to_analyse == []:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': NoValidFiles',
                    'reason': 'No files with .apk or .dex extension found in '
                              + self.path_app_folder
                              + '.'
                }
            )
        logging.debug(
            str(len(apps_to_analyse))
            + ' app(s) to analyse, using '
            + str(self.num_analysis_instances)
            + ' thread(s).'
        )

        # List and counter for keeping track of worker processes.
        self.process_list = []
        num_processes = 0
        
        # Create two process queues: one for sending data to,
        #  and one for receiving data from, worker processes.
        process_send_queue = JoinableQueue()
        process_receive_queue = JoinableQueue()
        
        # Create an object to keep track of apps currently being analysed.
        # This is mainly for status logging and for handling zombie processes.
        obj_current_analyses = {}
        
        # Create worker processes.
        for _ in range(0, self.num_analysis_instances):
            # Instantiate WorkerAnalyseApp class.
            worker_analyse = WorkerAnalyseApp(
                self.path_base_dir,
                self.path_script_dir,
                self.path_app_folder,
                self.master_bug_object,
                self.bool_generate_graph
            )

            # Create worker process with target method of
            #  WorkerAnalyseApp.fn_perform_analysis()
            worker = Process(
                target=worker_analyse.fn_perform_analysis,
                args=(
                    process_send_queue,
                    process_receive_queue,
                    num_processes
                )
            )
            
            # Start the worker process and append to process list.
            worker.start()
            self.process_list.append(worker)

            logging.debug(
                'Created worker process '
                + str(num_processes)
            )

            # Create a key for this worker.
            obj_current_analyses[num_processes] = ''
            num_processes += 1

        # Send work to worker processes by putting them on the Send Queue.
        for app_path in apps_to_analyse:
            process_send_queue.put(str(app_path))

        # Variable to keep track of how many analyses have completed.
        completed_app_count = 0
        
        # Continuously check status.
        while True:
            # Get information sent by worker process.
            [app_filename, result, error] = \
                process_receive_queue.get()
            
            # Let the worker process know that the data has been
            #  received and that the task is considered Done.
            process_receive_queue.task_done()

            # Analyse the output.
            # In addition to the actual analysis output, there are a number 
            #  of other messages that can be sent by the worker process. 
            #  The type of message returned is identified by the poorly-named
            #  "error" variable.
            # ----------------------------------------
            # If "error" is None, this is the actual analysis output.
            if error == None:
                logging.debug(
                    'Finished analysing '
                    + app_filename
                    + ' with output '
                    + str(result)
                    + '.'
                )

                # Write output to JSON files,
                #  regardless of whether we graph or not.
                apk_output_filename = app_filename.replace('.apk', '')
                apk_output_filename = apk_output_filename.replace('.', '_')
                apk_output_filename = os.path.join(
                    self.path_base_dir,
                    'output',
                    'raw',
                    apk_output_filename + '.json'
                )
                with open(apk_output_filename, 'w') as f:
                    json.dump(result, f, ensure_ascii=False, indent=4)
                    
                # Update graph.
                if self.bool_generate_graph == True:
                    if self.graph_type in ['neo4j', 'both']:
                        self.inst_graph_helper_main.fn_update_graph(
                            app_filename,
                            result[RESULT_KEY_GRAPHABLES]
                        )
                    self.master_output_object[app_filename] = result
                
            # ----------------------------------------
            # The worker process will send a status update for each app, to
            #  let the main process know which app is currently being analysed.
            elif error == 'status':
                # "app_filename" is not accurate here.
                # It's actually filepath.
                # "result" holds the process id.
                obj_current_analyses[result] = app_filename
                continue
            # ----------------------------------------
            # The worker process may also send logging messages.
            elif(error[0:8] == 'logging.'):
                worker_log_level = error[8:]
                worker_log_message = result
                logging.log(
                    LEVELS[worker_log_level.lower()],
                    worker_log_message
                )
                continue
            # ----------------------------------------
            # If error is not None, "status", or "logging", then
            #  something must have gone wrong.
            else:
                logging.warning(
                    'Error analysing '
                    + app_filename
                    + ': ['
                    + result
                    + '] '
                    + error
                    + '.'
                )

            # Check if any worker processes have become zombies.
            # This can happen sometimes if lack of memory
            #  causes a process to be killed.
            if len(active_children()) < self.num_analysis_instances:
                for p_index, p in enumerate(self.process_list):
                    if not p.is_alive():
                        logging.warning('Zombie process. Replacing.')
                        logging.debug(str(p))
                        # We want to maintain indices.
                        # Create a new process in its place.
                        logging.debug('Creating new process.')
                        worker_analyse = WorkerAnalyseApp(
                            self.path_base_dir,
                            self.path_script_dir,
                            self.path_app_folder,
                            self.master_bug_object,
                            self.bool_generate_graph
                        )
                        replacement_worker = Process(
                            target=worker_analyse.fn_perform_analysis,
                            args=(
                                process_send_queue,
                                process_receive_queue,
                                num_processes
                            )
                        )
                        replacement_worker.start()
                        self.process_list.append(replacement_worker)
                        logging.debug(
                            'Created replacement worker process '
                            + str(num_processes)
                        )
                        # Create a key for this worker.
                        obj_current_analyses[num_processes] = ''
                        # Get the app that was being analysed and add
                        #  back to queue.
                        failed_apk = obj_current_analyses[p_index]
                        process_send_queue.put(str(failed_apk))
                        # Increment process count.
                        num_processes += 1

            # Check if all apps have been analysed.
            completed_app_count += 1
            if completed_app_count == len(apps_to_analyse):
                break
        logging.info('Finished analysing apps.')

        # Tell all worker processes to stop.
        for _ in range(self.num_analysis_instances):
            process_send_queue.put('STOP')
            
        # Add relationships to graph.
        if self.bool_generate_graph == True:
            if self.graph_type in ['neo4j', 'both']:
                self.inst_graph_helper_main.fn_final_update_graph()
            if self.graph_type in ['visjs', 'both']:
                self.fn_create_custom_graph()

    def fn_exit_gracefully(self, signum, frame):
        for process in self.process_list:
            process.kill()
            
    def fn_create_custom_graph(self):
        self.inst_custom_grapher.fn_create_custom_graph(
            self.path_base_dir,
            self.master_output_object
        )

class WorkerAnalyseApp:
    """The app analysis class that performs the actual analysis."""

    def __init__(self, base_dir, script_dir, app_dir,
                 bug_obj, bool_gen_graph):
        """Sets paths and initialises variables.
        
        :param base_dir: string specifying location of script base directory
        :param script_dir: string specifying location of script directory
        :param app_dir: string specifying path to directory containing 
            applications to be analysed
        :param bug_obj: the "master bug object" (dictionary)
        :param bool_gen_graph: boolean value indicating whether or not a graph 
            should be generated
        """
        self.process_id = None
        self.out_queue = None       
        
        # Set paths.
        self.path_base_dir = base_dir
        self.path_app_folder = app_dir
        self.master_bug_object = bug_obj
        self.bool_generate_graph = bool_gen_graph

        # Initialise objects/values for the current app being analysed.
        self.current_app_filename = None
        self.current_app_filepath = None
        self.current_app_filesize = 0
        self.current_app_package_name = None
        self.current_apk_manifest = None
        self.current_app_bug_obj = {}

        # Initialise Androguard values for current app.
        self.androguard_apk_obj = None
        self.androguard_d_array = None
        self.androguard_dx = None

    def fn_reset(self):
        self.androguard_apk_obj = None
        self.androguard_d_array = None
        self.androguard_dx = None
        
    def fn_perform_analysis(self, in_queue, out_queue, process_id):
        """Gets apps from queue, analyses and returns result/error.
        
        :param in_queue: multiprocessing.Queue object to receive data from 
            parent process
        :param out_queue: multiprocessing.Queue object to send data to 
            parent process
        :param process_id: integer value representing the worker process's ID
        """
        # Set own process ID
        self.process_id = process_id
        # Make out queue an attribute, so that it can be accessed by other
        #  functions.
        self.out_queue = out_queue

        # Get values from input queue. When 'STOP' is received,
        #  stop listening on queue.
        for queue_input in iter(in_queue.get, 'STOP'):
            # First reset all values.
            self.current_app_filename = None
            self.current_app_filepath = None
            self.current_app_filesize = 0
            self.current_app_package_name = None
            self.current_apk_manifest = None
            self.current_app_bug_obj = {}
            self.androguard_apk_obj = None
            self.androguard_d_array = None
            self.androguard_dx = None

            # Start timer.
            self.start_time = timeit.default_timer()
        
            # Get value from input queue.
            self.current_app_filepath = str(queue_input).strip()

            # Let main know which job the worker is working on.
            self.out_queue.put([
                self.current_app_filepath,
                process_id,
                'status'
            ])
            
            # Get filesize for performance profiling.
            app_size_in_bytes = os.path.getsize(
                self.current_app_filepath
            )
            self.current_app_filesize = int(app_size_in_bytes)/1048576

            # Start initialising some values.
            _, app_filename = os.path.split(self.current_app_filepath)
            self.current_app_filename = app_filename

            # Debug string
            debug_string = (
                'Analysing '
                + app_filename
                + ' in worker thread '
                + str(self.process_id)
                + '.'
            )
            self.out_queue.put([
                self.current_app_filename,
                debug_string,
                'logging.info'
            ])

            # Create a "bug object" per app.
            self.fn_initialise_bug_obj()
            
            # Start Androguard.
            if self.current_app_filepath.endswith('.apk'):
                try:
                    self.androguard_apk_obj, \
                    self.androguard_d_array, \
                    self.androguard_dx = \
                    AnalyzeAPK(
                        self.current_app_filepath,
                        session=None
                    )
                except Exception as e:
                    result = 'AnalyzeAPKError'
                    error = str(e)
                    self.out_queue.put(
                        [self.current_app_filename, result, error]
                    )
                    in_queue.task_done()
                    gc.collect()
                    continue
            elif self.current_app_filepath.endswith('.dex'):
                try:
                    _, \
                    self.androguard_d_array, \
                    self.androguard_dx = \
                    AnalyzeDex(
                        self.current_app_filepath,
                        session=None
                    )
                except Exception as e:
                    result = 'AnalyzeDEXError'
                    error = str(e)
                    self.out_queue.put(
                        [self.current_app_filename, result, error]
                    )
                    in_queue.task_done()
                    gc.collect()
                    continue
            else:
                self.out_queue.put([
                    self.current_app_filename,
                    'Unrecognised file type',
                    'logging.error'
                ])
                in_queue.task_done()
                gc.collect()
                continue

            # Check current memory usage.
            #  But don't worry if it fails.
            try:
                self.fn_profile_memory()
            except:
                pass
                
            # Get package name from APK object or use filename when
            #  APK object does not exist.
            if self.androguard_apk_obj != None:
                self.current_app_package_name = \
                    self.androguard_apk_obj.get_package()
            else:
                self.current_app_package_name = \
                    self.current_app_filename

            # Initialise a list to graphable elements.
            self.current_graph_elements = []

            # Call the main analysis function.
            try:
                # Perform the analysis.
                self.fn_per_bug_analysis()
                
                # Log details about timing.
                elapsed_time = timeit.default_timer() - self.start_time
                timing_message = str(self.current_app_filename) \
                               + ' took ' \
                               + str(int(elapsed_time)) \
                               + ' seconds' \
                               + ' to analyse.'
                self.out_queue.put([
                    self.current_app_filename,
                    timing_message,
                    'logging.debug'
                ])
                
                # Put output of analysis onto out_queue.            
                self.out_queue.put([
                    self.current_app_filename,
                    {
                        RESULT_KEY_BUG_OBJ: self.current_app_bug_obj,
                        RESULT_KEY_GRAPHABLES: self.current_graph_elements
                    },
                    None
                ])
            # If analysis fails.
            except JandroidException as e:
                result = e.args[0]['type']
                error = e.args[0]['reason']
                # Put error onto out_queue.            
                self.out_queue.put([
                    self.current_app_filename,
                    result,
                    error
                ])

            # Let parent process know that we are done with this file.
            in_queue.task_done()
            self.fn_reset()
            gc.collect()
            continue

    def fn_profile_memory(self):
        """Determines approximate memory usage for the current app."""
        import psutil

        process = psutil.Process(os.getpid())
        mem_usage = int(process.memory_info().rss)/1048576
        memory_profile_string = (
            str(int(mem_usage))
            + 'MB memory used for app '
            + str(self.current_app_filename)
            + ' of size '
            + str(int(self.current_app_filesize))
            + 'MB.'
        )
        self.out_queue.put([
            self.current_app_filename,
            memory_profile_string,
            'logging.debug'
        ])

    def fn_initialise_bug_obj(self):
        """Creates object to track how many bugs an app matches."""
        #  Essentially this is an object with a key per bug.
        self.current_app_bug_obj = {}
        for bug in self.master_bug_object:
            self.current_app_bug_obj[bug] = False

    def fn_per_bug_analysis(self):
        """For an app, tests for the presence of each bug.
        
        If all bug elements are satisfied, then it calls functions to process 
        graphable elements.
        """
        for bug in self.master_bug_object:
            # Debug string.
            debug_string = 'Analysing bug ' + str(bug)
            self.out_queue.put([
                self.current_app_filename,
                debug_string,
                'logging.debug'
            ])

            # Initialise variables.
            # Variable to hold the number of bug elements we have to look for.
            # This will be incremented during the actual analyses.
            self.current_bug_search_types = 0
            # Variable to hold the number of bugs that have been matched.
            self.current_bug_search_outcomes = 0
            # List to store RETURN objects.
            self.current_returns = []
            # Object to store link parameters
            #  (between different types of searches).
            self.current_links = {}

            # Start search enumeration.
            for searchparams_key in \
                    self.master_bug_object[bug]:
                if searchparams_key == 'MANIFESTPARAMS':
                    self.fn_handle_manifest_analysis(bug)
                if searchparams_key == 'CODEPARAMS':
                    self.fn_handle_code_analysis(bug)
            
            # The bug element count and satisfied count will have been
            #  incremented during the analysis. If they are equal, then
            #  all searchable elements were matched, i.e., the bug template
            #  was satisfied.
            if (self.current_bug_search_types == \
                    self.current_bug_search_outcomes):
                self.current_app_bug_obj[bug] = True

                # We process graphables only if the outcome is True.
                # The fact that we are in this if condition means the outcome
                #  was True.
                if 'GRAPH' in self.master_bug_object[bug]:
                    self.fn_process_graphables(bug)

    def fn_handle_manifest_analysis(self, bug):
        """Calls the manifest analysis script based on bug template.
        
        This function goes through the bug template (for a specific bug) and 
        if it encountered a MANIFESTPARAMS key (which indicates that manifest 
        analysis should be performed), it increments the variable that keeps 
        track of the number of bug elements that have to be satisfied.
        
        If the manifest analysis returns True, then this function also 
        increments the variable that keeps track of the bug elements that have 
        been satisfied.
        
        :param bug: current bug being analysed.
        """
        manifest_obj = self.master_bug_object[bug]['MANIFESTPARAMS']
        # If there is no manifest search to perform, return.
        if manifest_obj == {}:
            return

        # If there is a manifest search to perform,
        #  increment the number of search types.
        self.current_bug_search_types +=1

        # If we are performing dex analysis, the Androguard APK
        #  object will be none.
        if self.androguard_apk_obj == None:
            return

        # Get the AndroidManifest.xml as a string.
        axml = self.androguard_apk_obj.get_android_manifest_axml()
        manifest_string = axml.get_xml()
        axml = None

        # Call the manifest analysis function.
        self.manifest_analyser = ManifestAnalyser(self.path_base_dir)
        [manifest_output, self.current_links] = \
            self.manifest_analyser.fn_perform_manifest_analysis(
                self.current_app_package_name,
                self.master_bug_object[bug],
                manifest_string,
                self.current_links
            )
        self.manifest_analyser = None
        
        # If the analysis output is True, increment the 
        #  "satisfied bug element" count.
        if manifest_output == True:
            self.current_bug_search_outcomes += 1

    def fn_handle_code_analysis(self, bug):
        """Calls the code analysis script.
        
        This function goes through the bug template (for a specific bug) and 
        if it encountered a CODEPARAMS key (which indicates that code 
        analysis should be performed), it increments the variable that keeps 
        track of the number of bug elements that have to be satisfied.
        
        If the code analysis returns True, then this function also 
        increments the variable that keeps track of the bug elements that have 
        been satisfied.
        
        :param bug: current bug being analysed.
        """
        # If there is no code search to be performed, return.
        code_obj = self.master_bug_object[bug]['CODEPARAMS']
        if code_obj == {}:
            return

        # If code search is to be performed,
        #  increment the number of search types.
        self.current_bug_search_types +=1
    
        # Call the code analysis function.
        self.code_analyser = CodeAnalyser(self.path_base_dir)
        [code_output, self.current_links] = \
            self.code_analyser.fn_perform_code_analysis(
                self.current_app_package_name,
                self.master_bug_object[bug],
                self.androguard_apk_obj,
                self.androguard_d_array,
                self.androguard_dx,
                self.current_links
            )
        self.code_analyser = None
        
        # If the analysis output is True, increment the 
        #  "satisfied bug element" count.
        if code_output == True:
            self.current_bug_search_outcomes += 1

    def fn_process_graphables(self, bug):
        """Processes the elements that are to be added to the graph.
        
        :param bug: current bug being analysed.
        """
        graph_obj = self.master_bug_object[bug]['GRAPH']
        # If there is no graphing key in the template, return.
        if graph_obj == []:
            return

        # Instantiate the GraphHelperWorker, which performs the actual
        #  processing, and call the processing function.
        inst_graph_helper_worker = GraphHelperWorker(self.path_base_dir)
        graphables = inst_graph_helper_worker.fn_analyse_graph_elements(
            graph_obj,
            self.current_links,
            self.current_app_package_name,
            bug
        )

        # Add output to the list of graphable elements.
        self.current_graph_elements.append(graphables)
            
