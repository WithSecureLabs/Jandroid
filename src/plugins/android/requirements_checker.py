import os
import logging
import platform


class RequirementsChecker:
    def __init__(self, base_dir, app_dir):
        """Sets paths.
        
        :param base_dir: string specifying path to script base directory
        :param app_dir: script specifying path to app directory
        """
        self.path_base_dir = base_dir
        self.path_app_folder = app_dir
        self.path_platform_tools = None
        
    def fn_perform_initial_checks(self, bool_pull_apps, app_pull_src):
        """Checks for existence of required files and folders.
        
        :param bool_pull_apps: boolean indicating whether apps are to be 
            pulled from device/image
        :param app_pull_src: string specifying pull location. Can be one 
            of "device", "img" or "ext4"
        :returns: string specifying path to ADB platform tools
        :raises JandroidException: an exception is raised if the app folder 
            is not present, or if it is empty (only when bool_pull_apps is 
            False)
        """
        logging.info('Performing basic checks. Please wait.')
        self.bool_pull_apps = bool_pull_apps
        self.pull_source = app_pull_src

        # Check app folder.
        # First check if the folder exists at all.
        if not os.path.isdir(self.path_app_folder):
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': DirectoryNotPresent',
                    'reason': 'App directory "'
                              + self.path_app_folder
                              + '" does not exist.'
                }
            )

        # Check if the folder has APK or DEX files inside.
        # Only do this if we are not expected to pull apps.
        if self.bool_pull_apps == False:
            if [f for f in os.listdir(self.path_app_folder)
                    if ((f.endswith('.apk') or
                        f.endswith('.dex'))
                    and not f.startswith('.'))] == []:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': EmptyAppDirectory',
                        'reason': 'App directory "'
                                  + self.path_app_folder
                                  + '" does not contain APK/DEX files.'
                    }
                )

        # If we *are* expected to pull apps, then if we are pulling
        #  from device, make sure we have Android platform-tools.
        else:
            if self.pull_source == 'device':
                self.fn_check_for_adb_executable()

        logging.info('Basic checks complete.')
        return self.path_platform_tools

    def fn_check_for_adb_executable(self):
        """Checks whether the ADB executable exists.
        
        This function identifies the execution platform, i.e., Windows, 
        Linux, or Mac (Darwin). It then creates the expected filepath to 
        the ADB executable and tests for whether the file is present in 
        the expected location (it expects the executable to be included 
        with the code, rather than being available somewhere on the system).
        
        :raises JandroidException: an exception is raised if the ADB 
            executable is not found at the expected location
        """
        # Get execution platform. ADB differs based on platform.
        run_platform = platform.system().lower().strip()
        logging.debug(
            'Platform identified as "'
            + run_platform + '".'
        )
        # Path to ADB.
        if run_platform == 'windows':
            executable = 'adb.exe'
        else:
            executable = 'adb'
        self.path_platform_tools = os.path.join(
            self.path_base_dir,
            'libs',
            'platform-tools',
            'platform-tools_' + run_platform,
            executable
        )
        if os.path.isfile(self.path_platform_tools):
            logging.debug(
                'Using adb tool at '
                + self.path_platform_tools
                + '.'
            )
        else:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': ADBNotPresent',
                    'reason': 'Could not find adb tool at '
                              + self.path_platform_tools
                              + '.'
                }
            )