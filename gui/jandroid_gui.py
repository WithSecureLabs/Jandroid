import os
import io
import re
import sys
import json
import random
import signal
import logging
import platform
import subprocess
import webbrowser
import configparser
from time import sleep
from multiprocessing import Process
from contextlib import redirect_stdout, redirect_stderr

from colorama import init as colorama_init
from colorama import Fore, Back, Style
        
from appJar import gui


STR_PULL_SRC_TITLE = 'pull_title'
STR_PULL_SRC = 'pull_src'
STR_PULL_TEXT = 'pull_text'

MAX_FIELD_LIMIT = 100

KEYWORDS = ['@app', '@tracepath']
INVALID_INPUT = {
    'len_long': 'Limit is ' + str(MAX_FIELD_LIMIT) + 'characters.',
    'len_blank': 'Field cannot be left blank.',
    'invalid_chars': 'Only alphabetic characters, digits and underscores can be used.',
    'reserved': 'Reserved keyword used as RETURN identifier. '
                + 'Identifier cannot be any of ' 
                + str(KEYWORDS) + '.',
    'return_exists': 'Return identifier musr be unique.'
}


class JandroidGui:
    """Class to create a basic GUI, to configure and execute Jandroid."""
    
    def __init__(self):
        """Sets default values and paths."""
        print('Setting up GUI components. Please wait. '
              + 'This can take up to a few minutes.\n')
        
        self.banner_off = False
        if len(sys.argv) > 1:
            if sys.argv[1] == '-s':
                self.banner_off = True
        # Initialise colorama, in case we want coloured text for anything.
        colorama_init()
        
        # Switch off appjar's logging.
        logging.getLogger('appJar').setLevel(logging.CRITICAL)

        # Appearance-related defaults.
        # Fonts.
        self.default_font_size = 10
        self.default_font_family = 'Tahoma'
        
        # Padding.
        self.default_horizontal_padding = 25
        self.default_vertical_padding = 20
        
        # Colours.
        # Window colour.
        self.colour_main_background = '#eef2f5'
        self.colour_main_foreground = '#414c58'
        # Buttons.
        self.colour_button_background = '#fa8e4a' #'#4a95c4' # Blue
        self.colour_button_foreground = '#ffffff'
        self.colour_button_active = '#f4a675'     #'#00bdd9' #   
        # Labels.
        self.colour_main_title_background = '#414c58'
        self.colour_main_title_foreground = '#ffffff'
        self.colour_sub_title_background = '#aeb7c2'  
        self.colour_sub_title_foreground = '#ffffff'
        # Fields.
        self.colour_field_background = '#ffffff'
        self.colour_field_foreground = '#414c58' #'#111111'
        self.colour_field_highlight = '#1fc3b3'
        self.colour_field_highlight_fg = '#ffffff'

        # The platform of the machine the script is running on.
        self.execution_platform = platform.system().lower().strip()
        
        # A default value for the platform (apps) to be analysed.
        self.default_analysis_platform = 'android'
        
        # Set paths.
        # The location of the (current) GUI script.
        self.path_current_dir = os.path.dirname(os.path.abspath(__file__))
        # The parent directory.
        self.path_base_dir = os.path.join(
            self.path_current_dir,
            '../'
        )
        
        # Image resource location.
        self.path_images = os.path.join(
            self.path_current_dir,
            'resources',
            'custom/'
        )
        
        # Location of config file.
        self.config_file = os.path.join(
            self.path_base_dir,
            'config',
            'jandroid.conf'
        )
        
        # Platform options.
        self.available_platforms = {
            'android': {
                STR_PULL_SRC_TITLE: 'Extract apps?',
                STR_PULL_SRC: [None, 'device', 'ext4', 'img'],
                STR_PULL_TEXT: [
                    'Don\'t extract (APKs already exist)',
                    'Extract APKs from device',
                    'Extract APKs from .ext4',
                    'Extract APKs from .img'
                ]
            }
        }
        
        # Set defaults.
        self.bool_analysis_in_progress = False
        self.jandroid_process = None
        self.analysis_platform = self.default_analysis_platform
        self.bool_generate_graph = False
        self.graph_type = 'visjs'
        
        # Load random banner.
        if self.banner_off == False:
            self.fn_load_banner()
        
        # Load manifest related options.
        manifest_json_path = os.path.join(
            self.path_current_dir,
            'files',
            'android_manifest.json'
        )
        self.manifest_tags = json.load(open(manifest_json_path, 'r'))
        
        # Variables for return lists (to update associates entry fields).
        self.current_listener = None
        self.current_top_window = None
        self.current_returns_window = None
        
        # Maintain a list of returns/links.
        self.current_returns = []
        
        # This is a hack to allow us to send ctrl+c to child process
        #  without terminating the main process.
        self.bool_preserve_main_process = False
        
        # Handle terminate events.
        signal.signal(signal.SIGINT, self.fn_handle_main_window_close)
        signal.signal(signal.SIGTERM, self.fn_handle_main_window_close)
        
    def main(self):
        """Calls functions to perform basic checks and create GUI."""
        # First create a basic frame.
        self.fn_create_main_window()
        # We don't want trace messages.
        self.main_window.setLogLevel('CRITICAL')
        
        # Check that we are using a compatible version of Python.
        # Else, display error and quit.
        python_version_ok = self.fn_check_python_version()
        if python_version_ok == False:
            self.main_window.errorBox(
                'error_bad_python_version',
                'Sorry, this script doesn\'t work with '
                + 'Python versions lower than v3.4.'
            )
            sys.exit(1)

        # If the Python version is ok, proceed with creating
        #  the rest of the GUI.
        self.fn_create_gui_components()

        # Open the window.
        self.main_window.go()
    
    """ =============== Standardised GUI components =============== """
    
    def fn_apply_standard_window_formatting(self, width=800, height=500):
        """Sets default values for newly created windows.
        
        :param width: width of the window (default 800)
        :param height: height of the window (default 500)
        """
        self.main_window.setSize(width, height)
        self.main_window.setBg(self.colour_main_background)
        self.main_window.setFg(self.colour_main_foreground)
        self.main_window.setResizable(canResize=False)
        self.main_window.setLocation('CENTER')        
        self.main_window.setGuiPadding(
            self.default_horizontal_padding,
            self.default_vertical_padding
        )
        self.main_window.setFont(
            self.default_font_size,
            family=self.default_font_family
        )
    
    def fn_create_standard_frame(self, frame_name, row=None, column=0):
        """Creates a frame with standard formatting.
        
        :param frame_name: string name for the frame
        :param row: integer row position within grid
        :param column: integer column position within grid
        """
        # If row is not given, we assume column isn't either.
        # Create a normal frame.
        if row == None:
            self.main_window.startFrame(
                frame_name
            ).config(bg=self.colour_main_background)
        # If row is specified, create a positioned frame.
        else:
            self.main_window.startFrame(
                frame_name,
                row=row,
                column=column
            ).config(bg=self.colour_main_background)
    
    def fn_create_standard_label(self, label_name, label_text,
                                 row=None, column=0):
        """Creates a label with standard formatting.
        
        :param label_name: string name for label
        :param label_text: string text to be displayed on label
        """
        if row == None:
            self.main_window.addLabel(
                label_name,
                label_text
            )
        else:
            self.main_window.addLabel(
                label_name,
                label_text,
                row=row,
                column=column
            )
        # Apply formatting.
        self.main_window.setLabelFg(
            label_name,
            self.colour_main_foreground
        )
        self.main_window.setLabelBg(
            label_name,
            self.colour_main_background
        )
        
    def fn_create_standard_status_label(self, label_name):
        """Creates a label with standard formatting, for status messages."""
        self.main_window.addLabel(
            label_name,
            ''
        ).config(
            bg=self.colour_main_background,
            fg='red',
            font='Tahoma 8 italic',
            anchor='w'
        )
        
    def fn_create_standard_radio_button(self, radio_button_group,
                                        radio_button_value, row=None,
                                        column=0):
        """Creates a radio button with standard formatting.
        
        :param radio_button_group: string name of the radio button group
        :param radio_button_value: string value for inidividual radio button
        """
        if row == None:
            self.main_window.addRadioButton(
                radio_button_group,
                radio_button_value
            )
        else:
            self.main_window.addRadioButton(
                radio_button_group,
                radio_button_value,
                row=row,
                column=column
            )
        self.main_window.setRadioButtonFg(
            radio_button_group,
            self.colour_main_foreground
        )
        self.main_window.setRadioButtonBg(
            radio_button_group,
            self.colour_main_background
        )
    
    def fn_create_standard_radio_box(self, radio_button_group,
                                     radio_button_value, row=None,
                                     column=0):
        """Creates a radio button "box" with standard formatting.
        
        :param radio_button_group: string name of the radio button group
        :param radio_button_value: string value for inidividual radio button
        """
        if row == None:
            self.main_window.addRadioButton(
                radio_button_group,
                radio_button_value
            ).config(
                indicatoron=0,
                background=self.colour_button_background,
                foreground=self.colour_button_foreground,
                selectcolor=self.colour_button_active,
                highlightbackground='#000000',
                highlightcolor='#000000',
                activebackground=self.colour_button_active,
                activeforeground=self.colour_button_foreground,
            )
        else:
            self.main_window.addRadioButton(
                radio_button_group,
                radio_button_value,
                row=row,
                column=column
            ).config(
                indicatoron=0,
                background=self.colour_button_background,
                foreground=self.colour_button_foreground,
                selectcolor=self.colour_button_active,
                highlightbackground='#000000',
                highlightcolor='#000000',
                activebackground=self.colour_button_active,
                activeforeground=self.colour_button_foreground,
            )

    def fn_create_standard_button(self, name=None, title=None, func=None,
                                  row=None, column=0, colspan=0, rowspan=0):
        """Creates a button with standard formatting.
        
        :param name: string value to be displayed within button
        :param title: string value to be used to reference button
        :param func: function reference
        :param row: integer row position within grid
        :param column: integer column position within grid
        :param colspan: integer value specifying number of columns to span
        :param rowspan: integer value specifying number of rows to span
        """
        if name==None:
            self.main_window.addButton(
                title=title,
                func=func,
                row=row,
                column=column,
                rowspan=rowspan,
                colspan=colspan
            )
        else:
            self.main_window.addNamedButton(
                name=name,
                title=title,
                func=func,
                row=row,
                column=column,
                rowspan=rowspan,
                colspan=colspan
            )
        
        # Apply formatting.
        self.main_window.setButtonFg(
            title,
            self.colour_button_foreground
        )
        self.main_window.setButtonBg(
            title,
            self.colour_button_background
        )
        self.main_window.setButtonRelief(
            title,
            'raised'
        )
    
    def fn_create_standard_returns_button(self, title, row=None,
                                          column=0, func=None):
        """Creates a standard button for opening a window of link items.
        
        :param title: string identifier for the button
        :param row: integer row position within grid
        :param column: integer column position within grid
        :param func: function to call when the button is clicked
        """
        if row == None:
            self.main_window.addNamedButton(
                name='\u0B83',#'\u2731',
                func=func,
                title=title
            ).config(padx=-2, pady=-2)
        else:
            self.main_window.addNamedButton(
                name='\u0B83',#'\u2731',
                func=func,
                title=title,
                row=row,
                column=column
            ).config(padx=-2, pady=-2)    
        
    def fn_create_standard_main_title(self, label_name, label_content, 
                                      row=None, column=0, colspan=0,
                                      rowspan=0):
        """Adds a label with standard formatting.
        
        :param label_name: string value to reference label
        :param label_content: string value to display within label
        :param row: integer row position within grid
        :param column: integer column position within grid
        :param colspan: integer value specifying number of columns to span
        :param rowspan: integer value specifying number of rows to span
        """
        self.main_window.addLabel(
            label_name,
            label_content,
            row,
            column,
            colspan,
            rowspan
        )
        # Apply formatting.
        self.main_window.setLabelBg(
            label_name,
            self.colour_main_title_background
        )
        self.main_window.setLabelFg(
            label_name,
            self.colour_main_title_foreground
        )
    
    def fn_create_standard_entry(self, entry_field_name, entry_type=None,
                                 label=None, words=None, row=None, column=0,
                                 tooltip=None):
        """Creates an entry field, with standard formatting.
        
        :param entry_field_name: string identifier for the field
        :param entry_type: string type for entry field. Can be one of 'auto' 
            for auto-entry field, or 'directory' for directory selection field
        :param label: string value for label to be displayed alongside field
        :param words: list of values to be displayed, for auto-entry field
        :param row: integer row position within grid
        :param column: integer column position within grid
        """
        # Create an ordinary entry field.
        if entry_type == None:
            if label == None:
                if row == None:
                    self.main_window.addEntry(entry_field_name)
                else:
                    self.main_window.addEntry(
                        entry_field_name,
                        row=row,
                        column=column
                    )
            else:
                if row == None:
                    self.main_window.addLabelEntry(
                        entry_field_name,
                        label=label
                    )
                else:
                    self.main_window.addLabelEntry(
                        entry_field_name,
                        label=label,
                        row=row,
                        column=column
                    )
        # Create directory-selection field.
        elif entry_type == 'directory':
            if label == None:
                if row == None:
                    self.main_window.addDirectoryEntry(entry_field_name)
                else:
                    self.main_window.addDirectoryEntry(
                        entry_field_name,
                        row=row,
                        column=column
                    )
            else:
                if row == None:
                    self.main_window.addLabelDirectoryEntry(
                        entry_field_name,
                        label=label
                    )
                else:
                    self.main_window.addLabelDirectoryEntry(
                        entry_field_name,
                        label=label,
                        row=row,
                        column=column
                    )
        # Create auto-entry field.
        elif entry_type == 'auto':
            if label == None:
                if row == None:
                    self.main_window.addAutoEntry(
                        entry_field_name,
                        words=words
                    )
                else:
                    self.main_window.addAutoEntry(
                        entry_field_name,
                        words=words,
                        row=row,
                        column=column
                    )
            else:
                if row == None:
                    self.main_window.addLabelAutoEntry(
                        entry_field_name,
                        label=label,
                        words=words
                    )
                else:
                    self.main_window.addLabelAutoEntry(
                        entry_field_name,
                        label=label,
                        words=words,
                        row=row,
                        column=column
                    )
        # Create numeric field.
        elif entry_type == 'numeric':
            if label == None:
                if row == None:
                    self.main_window.addNumericEntry(
                        entry_field_name
                    )
                else:
                    self.main_window.addNumericEntry(
                        entry_field_name,
                        row=row,
                        column=column
                    )
            else:
                if row == None:
                    self.main_window.addLabelNumericEntry(
                        entry_field_name,
                        label=label
                    )
                else:
                    self.main_window.addLabelNumericEntry(
                        entry_field_name,
                        label=label,
                        row=row,
                        column=column
                    )

        # Apply formatting.
        self.main_window.setEntryFg(
            entry_field_name,
            self.colour_field_foreground
        )
        self.main_window.setEntryBg(
            entry_field_name,
            self.colour_field_background
        )
        self.main_window.setEntryInPadding(
            entry_field_name,
            [5, 5]
        )
        
        # Remove any error/invalid formatting if the user should start typing.
        self.main_window.setEntryChangeFunction(
            entry_field_name,
            self.fn_set_entry_valid
        )
        
        # If a tooltip has been specified, set it here. This will be displayed
        #  when the mouse hovers over the entry field.
        if tooltip != None:
            self.main_window.setEntryTooltip(
                entry_field_name,
                tooltip
            )
        
    def fn_set_entry_valid(self, entry_field_name, status_label_name=None):
        """Formats an entry field to show that the input text is valid.
        
        :param entry_field_name: string name of the entry field
        """
        self.main_window.getEntryWidget(
            entry_field_name
        ).config(
            fg=self.colour_main_foreground,
            highlightbackground=self.colour_main_background,
            highlightcolor=self.colour_main_background,
            highlightthickness='0'
        )
        
        if status_label_name != None:
            self.main_window.setLabel(
                status_label_name,
                ''
            )
        
    def fn_set_entry_invalid(self, entry_field_name, status_label_name=None,
                             label_status=None):
        """Formats an entry field to show that the input text is invalid.
        
        :param entry_field_name: the name of the entry field that is invalid
        """
        self.main_window.getEntryWidget(
            entry_field_name
        ).config(
            fg='#FF0000',
            highlightbackground='#FF0000',
            highlightcolor='#FF0000',
            highlightthickness='1'
        )
        
        if ((status_label_name != None) and (label_status != None)):
            self.main_window.setLabel(
                status_label_name,
                label_status
            )

    def fn_create_standard_textarea(self, textarea_name, text=None):
        """Creates a scrolled text area with standardised formatting.
        
        :param textarea_name: string identifier for text area
        :param text: string text to be displayed in text area
        """
        # Create a scrolled text area.
        self.main_window.addScrolledTextArea(textarea_name, text=text)
        
        # Apply standard formatting.
        self.main_window.setTextAreaFg(
            textarea_name,
            self.colour_field_foreground
        )
        self.main_window.setTextAreaBg(
            textarea_name,
            self.colour_field_background
        )

    def fn_create_standard_listbox(self, listbox_name, listbox_items):
        """Creates a list box with standardised formatting.
        
        :param listbox_name: string identifier for list box
        :param listbox_items: list of items to be displayed in the list box
        """
        # By default, Tkinter list boxes cannot have padding.
        # We want padding, so we create a frame and create the listbox
        #  within.
        self.fn_create_standard_frame(
            'frame_for_' + listbox_name
        )
        self.main_window.getFrameWidget(
            'frame_for_' + listbox_name
        ).config(
            bd=1,
            relief='sunken',
            background=self.colour_field_background,
            padx=5,
            pady=5
        )
        self.main_window.addListBox(
            listbox_name,
            listbox_items
        ).config(
            relief='flat',
            borderwidth=0,
            background=self.colour_field_background,
            foreground=self.colour_field_foreground,
            selectborderwidth=0,
            selectbackground=self.colour_field_highlight,
            selectforeground=self.colour_field_highlight_fg,
            highlightthickness=0,
            highlightbackground=self.colour_field_background,            
            activestyle='none'
        )
        self.main_window.stopFrame()
        self.main_window.setListBoxMulti(listbox_name, multi=False)
    
    def fn_create_standard_optionbox(self, optionbox_name, option_list,
                                     label=None, row=None, column=0):
        """Creates an optionbox with standard formatting.
        
        :param optionbox_name: string value to reference the option box
        :param option_list: list of values to display within option box
        :param label: string value to display alongside (left of) option box
        """
        if label != None:
            if row == None:
                self.main_window.addLabelOptionBox(
                    optionbox_name,
                    option_list,
                    label=label,
                    disabled='='
                )
            else:
                self.main_window.addLabelOptionBox(
                    optionbox_name,
                    option_list,
                    label=label,
                    row=row,
                    column=column,
                    disabled='='
                )
        else:
            if row == None:
                self.main_window.addOptionBox(
                    optionbox_name,
                    option_list,
                    disabled='='
                )
            else:
                self.main_window.addOptionBox(
                    optionbox_name,
                    option_list,
                    row=row,
                    column=column,
                    disabled='='
                )
        # Apply formatting.
        self.main_window.setOptionBoxFg(
            optionbox_name,
            self.colour_main_foreground
        )
        self.main_window.setOptionBoxBg(
            optionbox_name,
            self.colour_main_background
        )
        self.main_window.setOptionBoxActiveFg(
            optionbox_name,
            self.colour_main_foreground
        )
        self.main_window.setOptionBoxActiveBg(
            optionbox_name,
            self.colour_main_background
        )
        self.main_window.setOptionBoxInPadding(
            optionbox_name,
            [5, 5]
        )
    
    """ =============== GUI component creation =============== """
    
    def fn_create_main_window(self):
        """Creates the main GUI window, i.e., the landing page."""
        # Initialise the main appjar GUI element (i.e., the main window).
        self.main_window = gui(
            'Jandroid',
            handleArgs=False,
            showIcon=False
        )

        # Use standardised formatting with default values.
        self.fn_apply_standard_window_formatting(800, 550)
        
        # Window label.
        # We want a label that's slightly larger than the default text.
        self.fn_create_standard_main_title(
            'jandroid_title',
            'JANDROID'
        )
        self.main_window.getLabelWidget(
            'jandroid_title'
        ).config(font='Consolas 18')
        
        # Set a function to perform some checks and kill child processes
        #  before exiting.
        self.main_window.setStopFunction(self.fn_handle_main_window_close)

    def fn_create_gui_components(self):
        """Calls various methods to create GUI components."""
        #self.fn_add_menu_bar()
        self.fn_create_platform_selection_frame()
        self.fn_print_banner_line()
        self.fn_create_app_directory_selector()
        self.fn_print_banner_line()
        self.fn_create_graphing_options_section()
        self.fn_print_banner_line()
        self.fn_create_functional_button_rows()
        self.fn_print_banner_line()
        self.fn_create_statusbar()
        self.fn_print_banner_line()
        self.fn_create_log_window()
        self.fn_print_banner_line()
        self.fn_create_returns_window()
        self.fn_print_banner_line()
        self.fn_create_returns_from_trace_window()

    def fn_add_menu_bar(self):
        """Adds a menu bar to the top of the window."""
        self.main_window.addMenuItem(
            'Help',
            'What is Jandroid?',
            self.fn_show_menu_about_jandroid
        )

    def fn_create_platform_selection_frame(self):
        """Creates the topmost frame, which contains platform-related elements.
        
        The platform-selection frame allows the user to select the analysis 
        platform (*not* the execution platform, which is determined 
        programmatically). This frame also allows a user to select whether 
        they want to extract apps from a variety of sources.
        """
        # Outline for section.
        self.main_window.startLabelFrame('Platform-specific').config(
            fg=self.colour_main_foreground
        )
        
        # Make the columns expand and take up the entire width.
        self.main_window.setSticky('ew')
        # Pad internally.
        self.main_window.setPadding([25, 15])
 
        # "Parent" frame. It contains the left and right panes within it.
        # This was done because using the parent pane as left pane caused 
        #  alignment issues.
        self.fn_create_standard_frame('platform_specific_frame_parent', 0, 0)
        
        # Left pane - platform selection.
        self.fn_create_platform_selection_left_frame()

        # Right pane - app extraction pane.
        # This is actually a frame stack, i.e., multiple frames one on
        #  top of the other.
        self.fn_create_platform_selection_right_frame_stack()
        
        # End parent frame.
        self.main_window.stopFrame()
        
        # End section outline.
        self.main_window.stopLabelFrame()
    
    def fn_create_platform_selection_left_frame(self):
        """Creates the left internal frame within the platform section.
        
        This frame enables the user to select one of a number of possible 
        analysis platforms (only Android supported at present).
        The list of platforms is populated from a dictionary object declared 
        within <init>.
        """
        # Create the frame.
        self.fn_create_standard_frame('platform_specific_frame_left', 0, 0)
        # Make widgets "stick" to top left.
        self.main_window.setSticky('nw')
        # Force widgets to align to top.
        self.main_window.setStretch('COLUMN')
        
        # Main title for frame.
        self.main_window.addLabel(
            'platform_selection_label',
            'Select the analysis platform'
        ).config(
            fg=self.colour_main_foreground,
            anchor='w'
        )
        
        # Populate list of platforms as radio buttons.
        for available_platform in self.available_platforms:
            self.fn_create_standard_radio_button(
                'platform_radio',
                available_platform.capitalize()
            )
            
        # Set default selection.
        self.main_window.setRadioButton(
            'platform_radio',
            self.default_analysis_platform.capitalize(),
            callFunction=True
        )
        
        # Set function to handle radio button option change.
        self.main_window.setRadioButtonChangeFunction(
            'platform_radio',
            self.fn_on_platform_radiobutton_changed
        )
        
        # Complete creation of frame.
        self.main_window.stopFrame()

    def fn_create_platform_selection_right_frame_stack(self):
        """Creates the right internal frames within the platform section.
        
        This section enables the user to select app extraction options for 
        their chosen platform. The options are populated from a dictionary 
        object declared within <init>.
        
        A frame stack is created, with on frame for each platform, and the 
        frame corresponding to the default platform is brought to 
        the foreground.
        """
        # Create a frame per platform.
        for platform_option in self.available_platforms:
            self.fn_create_platform_selection_right_frame(platform_option)
            
        # Set one frame as default.
        self.main_window.raiseFrame(
            'platform_specific_frame_right_' + self.default_analysis_platform
        )
    
    def fn_create_platform_selection_right_frame(self, platform_option):
        """Creates a right internal frame within the platform section.
        
        This function creates a frame containing app extraction options 
        for a specific platform.
        
        :param platform_option: string value corresponding to an 
            analysis platform
        """
        # Create the frame.
        frame_name = 'platform_specific_frame_right_' + platform_option
        self.fn_create_standard_frame(frame_name, 0, 1)
        # Set widgets to "stick" to top left.
        self.main_window.setSticky('nw') 
        # Force widgets to align to top.
        self.main_window.setStretch('COLUMN')
        
        # Main title for frame.
        label_name = 'app_extraction_label_' + platform_option
        self.main_window.addLabel(
            label_name,
            self.available_platforms[platform_option][STR_PULL_SRC_TITLE]
        ).config(anchor='w')
        
        # Create pull app options.
        if STR_PULL_SRC in self.available_platforms[platform_option]:
            pull_options = \
                self.available_platforms[platform_option][STR_PULL_TEXT]
            for pull_option in pull_options:
                self.fn_create_standard_radio_button(
                    'platform_pull_src',
                    pull_option
                )
        
        # Finished creating frame.
        self.main_window.stopFrame()

    def fn_create_app_directory_selector(self):
        """Creates a section for selecting the app directory."""
        # Outline for section.
        self.main_window.startLabelFrame('Select app directory').config(
            fg=self.colour_main_foreground
        )
        # Make the columns expand and take up the entire width.
        self.main_window.setSticky('ew')        
        # Pad internally.
        self.main_window.setPadding([25, 15])

        # Create a directory selector widget        
        self.fn_create_standard_entry(
            'app_directory',
            entry_type='directory'
        )
        # Assign a default value of <base_dir>/apps/
        default_app_directory = os.path.normpath(os.path.join(
            self.path_base_dir,
            'apps/'
        ))
        self.main_window.setEntry('app_directory', default_app_directory)
        
        # End of outline.
        self.main_window.stopLabelFrame()

    def fn_create_graphing_options_section(self):
        """Creates a section for selecting whether or not to graph results."""
        # Outline for section. 
        self.main_window.startLabelFrame('Graph options').config(
            fg=self.colour_main_foreground
        )
        # Make the columns expand and take up the entire width.
        self.main_window.setSticky('ew')
        # Pad internally.
        self.main_window.setPadding([25, 15])

        # Create a checkbox.
        self.main_window.addCheckBox('Output to Neo4j?', 0, 0)
        self.main_window.addCheckBox('Output to custom graph?', 0, 1)
        self.main_window.addButton(
            title='Open Custom Graph',
            func=self.fn_open_graph_in_browser,
            row=0,
            column=2
        )
        self.main_window.disableButton('Open Custom Graph')
        # Set the checkbox to be checked by default,
        #  i.e., we graph by default.
        self.main_window.setCheckBox(
            'Output to Neo4j?',
            ticked=False,
            callFunction=False
        )
        self.main_window.setCheckBox(
            'Output to custom graph?',
            ticked=True,
            callFunction=False
        )
        
        # End of outline.
        self.main_window.stopLabelFrame()
    
    def fn_create_functional_button_rows(self):
        """Create two rows of buttons.
        
        This function creates two rows of buttons at the bottom of the 
        window (just above the status bar). The first row contains buttons 
        for Advanced Configuration, the Template Manager and the Log Viewer. 
        The second row contains a single button for starting/stopping the 
        analysis.
        """
        # Create subwindows for advanced configurations and for
        #  the template manager.
        self.fn_create_advanced_config_subwindow()
        self.fn_print_banner_line()
        self.fn_create_template_manager_subwindow()
        
        # Start the frame.
        self.fn_create_standard_frame('final_row')
        self.main_window.setSticky('ew')
        # Create the top row of 3 buttons.
        # The buttons will have some space between them, created
        #  artificially by inserting labels between two buttons.
        self.fn_create_standard_button(
            name='        Advanced Configuration        ',
            title='Advanced Configuration',
            func=self.fn_show_advanced_config_subwindow,
            row=0,
            column=0
        )
        self.main_window.addLabel(
            'label_functional_button_top_row_padding1',
            '',
            row=0,
            column=1
        )
        self.fn_create_standard_button(
            name='       Template Manager       ',
            title='Template Manager',
            func=self.fn_show_template_manager_subwindow,
            row=0,
            column=2
        )
        self.main_window.addLabel(
            'label_functional_button_top_row_padding2',
            '',
            row=0,
            column=3
        )
        self.fn_create_standard_button(
            name='         Analysis Log         ',
            title='Analysis Log',
            func=self.fn_show_log_window,
            row=0,
            column=4
        )
        
        # Leave a small space between the top and bottom rows of buttons
        #  (purely aesthetical).
        self.main_window.addLabel(
            'label_functional_button_inter_row_padding1',
            '',
            1
        ).config(font='Tahoma 1')
        
        self.main_window.setStretch('row')
        # Create the bottom button.
        self.fn_create_standard_button(
            title='Start Analysis',
            func=self.fn_start_stop_analysis,
            row=2,
            column=0,
            colspan=5
        )
            
        # Frame creation complete.
        self.main_window.stopFrame()
    
    def fn_create_advanced_config_subwindow(self):
        """Creates a subwindow within which the config file can be modified."""
        # Create the subwindow.
        self.main_window.startSubWindow('Advanced Configuration', modal=True)
        self.fn_apply_standard_window_formatting()
        self.main_window.setSticky('new')  
        self.main_window.setPadding([25, 10])          
        self.main_window.addLabel(
            'advanced_config',
            'Advanced Configuration'
        ).config(font='Tahoma 11 bold')        

        # Open and read the config file.
        config_file_text = open(self.config_file).read()
        
        # Create a scrolled text area.
        self.fn_create_standard_textarea('Config File', text=None)
        self.main_window.setTextAreaHeight('Config File', 18)
        self.main_window.setTextAreaWidth('Config File', 750)
        self.main_window.setTextAreaPadding('Config File', [15, 15])
        self.main_window.setTextAreaFont(
            'Config File',
            size=self.default_font_size,
            family=self.default_font_family
        )
        
        # Add the config file text to the text area.
        self.main_window.setTextArea(
            'Config File',
            text=config_file_text,
            end=False,
            callFunction=True
        )
        
        # Add a label informing the user that modifying the contents will
        #  modify the main config file.
        self.main_window.addLabel(
            'label_warning_for_config_modification',
            'Note: Modifying (and saving) this text will result in the '
            + 'config file being modified.'
        ).config(font='Tahoma 10 italic', anchor='w')
        
        self.main_window.setPadding([25, 20])
        
        # Create a button allowing the user to save the changes or cancel.
        self.fn_create_standard_frame('save_or_cancel')
        self.fn_create_standard_button(
            title='Save Config',
            name='             Save Config             ',
            func=self.fn_save_config_file,
            row=0,
            column=0
        )
        self.main_window.addLabel(
            'save_cancel_row_padding1',
            '',
            row=0,
            column=1
        )
        self.fn_create_standard_button(
            title='Cancel',
            name='               Cancel               ',
            func=self.fn_hide_advanced_config_subwindow,
            row=0,
            column=2
        )
        self.main_window.stopFrame()
        
        # Finished creating the subwindow.
        self.main_window.stopSubWindow()
    
    def fn_create_template_manager_subwindow(self):
        """Creates a subwindow for viewing and creating templates."""
        # Create the subwindow.
        self.main_window.startSubWindow('Template Manager', modal=True)
        self.fn_apply_standard_window_formatting()
        self.main_window.setSticky('new')
        self.main_window.setStretch('COLUMN')
        self.main_window.setPadding([25, 10])
        self.main_window.addLabel(
            'label_template_manager',
            'Template Manager'
        ).config(font='Tahoma 11 bold')

        self.fn_create_standard_frame('frame_templates_window_top_buttons')
        self.main_window.setSticky('news')
        # Add three labels which will emulate buttons.
        # The first will display existing templates.
        self.fn_create_standard_radio_box(
            'template_manager_radio_box_group',
            '               View Existing Templates               ',
            0,
            0
        )
        # Padding
        self.main_window.addLabel(
            'label_template_manager_button_padding1',
            '',
            0,
            1
        )
        # The second "button" will enable the creation of new templates.
        self.fn_create_standard_radio_box(
            'template_manager_radio_box_group',
            '                 Create New Template                 ',
            0,
            2
        )
        # Padding
        self.main_window.addLabel(
            'label_template_manager_button_padding2',
            '',
            0,
            3
        )
        # The third button will display information about templates and links.
        self.fn_create_standard_radio_box(
            'template_manager_radio_box_group',
            '            Template Help             ',
            0,
            4
        )
        self.main_window.setRadioButtonChangeFunction(
            'template_manager_radio_box_group',
            self.fn_handle_templatemanager_radio_box_change
        )
        self.fn_create_standard_label(
            'label_template_manager_button_row_padding',
            '',
            1,
            0
        )
        self.main_window.addHorizontalSeparator(2,0,5)
        self.main_window.stopFrame()

        self.fn_create_standard_frame('template_manager_outline')
        # Make the columns expand and take up the entire width.
        self.main_window.setSticky('news')
        # Pad internally.
        self.main_window.setPadding([0, 0])
        
        # Create three frames, one on top of the other.
        self.fn_create_existing_templates_frame()
        self.fn_print_banner_line()
        self.fn_create_new_template_frame()
        self.fn_print_banner_line()
        self.fn_create_template_help_frame()
        self.fn_print_banner_line()
        
        # Bring one frame to the foreground.
        self.main_window.raiseFrame('frame_existing_templates_parent')
        
        self.main_window.stopFrame()
        
        # Finished creating subwindow.
        self.main_window.stopSubWindow()

    def fn_create_existing_templates_frame(self):
        """Creates a frame to display details about existing templates.
        
        The frame will have two panes: the left pane will show a list of the 
        available templates, and the right pane will show the contents of 
        the currently selected template.
        """
        # Start the frame.
        self.fn_create_standard_frame('frame_existing_templates_parent', 4, 0)

        # Left pane - template list.
        self.fn_create_existing_templates_left_frame()
        
        # Right pane - template contents.
        self.fn_create_existing_templates_right_frame()
        
        # Populate data in existing templates.
        self.fn_populate_existing_templates()
        
        # Finished creating the frame.
        self.main_window.stopFrame()

    def fn_create_existing_templates_left_frame(self):
        """Creates the left pane for existing templates."""
        # Create the frame and apply formatting.
        self.fn_create_standard_frame('frame_existing_templates_left', 0, 0)
        self.main_window.setSticky('nw')
        self.main_window.setStretch('COLUMN')        
        self.main_window.addLabel(
            'label_existing_template_list',
            'Existing Templates'
        ).config(anchor='w')

        # Create a list box to display all the template names.
        self.fn_create_standard_listbox('Available Templates', None)
        # Set height, width.
        self.main_window.setListBoxWidth('Available Templates', 24)
        self.main_window.setListBoxHeight('Available Templates', 18)
        
        self.main_window.addLabel(
            'label_existing_template_create_padding1',
            ''
        ).config(font='Tahoma 8')
        
        self.main_window.stopFrame()
    
    def fn_create_existing_templates_right_frame(self):
        """Creates the right pane for existing templates."""
        # Create frame.
        self.fn_create_standard_frame('frame_existing_templates_right', 0, 1)
        self.main_window.setSticky('ne')
        self.main_window.setStretch('COLUMN')
        self.main_window.addLabel(
            'label_existing_template_content',
            'Template Content'
        ).config(anchor='w')
        
        # Create a textarea box with the template content.
        self.fn_create_standard_textarea('Template Content')
        self.main_window.setTextAreaHeight('Template Content', 21)
        self.main_window.setTextAreaWidth('Template Content', 81)
        self.main_window.setTextAreaPadding('Template Content', [15, 15])
        self.main_window.setTextAreaFont(
            'Template Content',
            size=8,
            family=self.default_font_family
        )
        
        # Finished creating frame.
        self.main_window.stopFrame()
        
    def fn_create_new_template_frame(self):
        """Creates a frame within which new templates can be generated.
        
        The frame will have two panes: the left pane will be where the user 
        inputs data, and the right is where the result will be displayed. 
        The result will be dynamically updated as the user types/selects.
        """
        # Create the frame.
        self.fn_create_standard_frame('frame_new_template_parent', 4, 0)
        
        # Left pane - template controls.
        self.fn_create_new_template_left_frame()
        
        # Right pane - dynamically updated output.
        self.fn_create_new_template_right_frame()   

        # Add elements to left frame. We do this out of order (i.e., add right
        #  frame to window before adding left frame elements), so that the
        #  update functionality works.
        self.fn_add_elements_to_new_template_left_frame()
        
        # Finished creating frame.
        self.main_window.stopFrame()

    def fn_create_new_template_left_frame(self):
        """Creates the left pane for new template creation."""
        # Create frame.
        self.fn_create_standard_frame('frame_new_template_left', 0, 0)
        self.main_window.setSticky('nw')
        self.main_window.setStretch('COLUMN')
        
        self.main_window.setPadding([(0, 15),0])        
        self.main_window.stopFrame()

    def fn_add_elements_to_new_template_left_frame(self):
        """Adds widgets to left frame.
        
        This is done in a separate function, because it references widgets in 
        the right frame, which means that the right frame (with the widgets) 
        must be created first. If the widgets in the left frame were added 
        when the left frame was created, then an error would be thrown 
        because widgets that have not yet been added (to the right frame) 
        would be being referenced.
        """
        self.main_window.openFrame('frame_new_template_left')
        self.main_window.startFrameStack('Template Creator')
        self.main_window.setStretch('COLUMN')
        # Frame for setting name and selecting manifest/code options.
        self.fn_create_new_template_stack_frame_start()

        # Frame for manifest analysis-related settings.
        # Disabled if the user didn't want manifest searches.
        self.fn_create_new_template_stack_frame_manifest()
        # This also has a subwindow.
        self.fn_create_new_manifest_rule_subwindow()
        self.fn_print_banner_line()

        # Frame for code analysis-related settings.
        # Disabled if the user didn't want code searches.
        self.fn_create_new_template_stack_frame_code()
        # This has two subwindows.
        self.fn_create_code_search_subwindow()
        self.fn_print_banner_line()
        self.fn_create_code_trace_subwindow()
        self.fn_print_banner_line()
        
        # Graphing options.
        self.fn_create_new_template_stack_frame_graph()
        self.fn_print_banner_line()
        
        # Confirmation window.
        self.fn_create_new_template_stack_frame_confirm()
        self.fn_print_banner_line()
        self.main_window.stopFrameStack()

        # Padding
        self.main_window.addLabel(
            'label_new_template_create_padding2',
            ''
        ).config(font='Tahoma 5')

        # Button row.
        self.main_window.addButtons(
            ['PREV', 'NEXT', 'RESET'],
            self.fn_handle_template_creation_stack
        )
        
        # Initialise everything.
        self.fn_reset_new_template_frame_stack()
        
        # Finished creating frame.
        self.main_window.stopFrame()
    
    def fn_create_new_template_stack_frame_start(self):
        """Creates a frame for setting template name and options."""
        self.fn_create_standard_frame('frame_new_template_stack_start')
        self.main_window.setSticky('new')
        self.main_window.setStretch('COLUMN')
        self.main_window.addLabel(
            'label_template_name',
            'Unique template name'
        ).config(
            bg=self.colour_main_background,
            fg=self.colour_main_foreground,
            anchor='w'
        )
        
        self.fn_create_standard_entry('Template Name')
        
        self.main_window.setSticky('new')
        # A label for displaying status (usually error) messages.
        self.fn_create_standard_status_label('label_template_name_status')
        
        # Initialise the entry and label elements.
        self.fn_reset_new_template_name_entry_to_wait()
        
        # Padding.
        self.main_window.addLabel(
            'label_template_create_padding1', ''
        ).config(
            font='Tahoma 3'
        )
        
        self.main_window.addLabel(
            'label_template_create_options',
            'Template options'
        ).config(
            bg=self.colour_main_background,
            fg=self.colour_main_foreground,
            anchor='w'
        )
        
        template_creation_options = [
            'Manifest search',
            'Code search/trace',
            'Manifest search & code search/trace'
        ]
        self.fn_create_standard_optionbox(
            'Template Options',
            template_creation_options
        )
        
        self.main_window.stopFrame()

    def fn_create_new_template_stack_frame_manifest(self):
        """Creates a frame to create the MANIFESTPARAMS section of template."""
        self.fn_create_standard_frame('frame_new_template_stack_manifest')
        self.main_window.setSticky('new')
        self.main_window.setStretch('COLUMN')
        self.main_window.addLabel(
            'label_manifest_settings',
            'Manifest analysis settings'
        ).config(
            bg=self.colour_main_background,
            fg=self.colour_main_foreground,
            anchor='w'
        )
        self.main_window.addLabel(
            'label_manifest_instructions',
            'Double-click a node to add a rule.'
        ).config(
            bg=self.colour_main_background,
            fg='#010101',
            font='Tahoma 8',
            anchor='w'
        )
        
        # Create a nested folder-like structure following the structure
        #  of an Android manifest XML file.
        android_manifest_xml = os.path.join(
            self.path_current_dir,
            'files',
            'android_manifest.xml'
        )
        manifest_tree = open(android_manifest_xml, 'r').read()
        # Redirect stderr to get rid of some printed warning messages
        #  from idlelib.
        f = io.StringIO()
        with redirect_stderr(f):
            self.main_window.addTree(
                'Android Manifest Tree',
                manifest_tree,
                rowspan = 1
            )
            # Set some formatting.
            self.main_window.setTreeBg(
                'Android Manifest Tree',
                self.colour_field_background
            )
            self.main_window.setTreeFg(
                'Android Manifest Tree',
                self.colour_field_foreground
            )
            self.main_window.setTreeHighlightBg(
                'Android Manifest Tree',
                self.colour_field_highlight
            )
            self.main_window.setTreeHighlightFg(
                'Android Manifest Tree',
                self.colour_field_highlight_fg
            )
        f = None
        
        # We don't want the user to be able to edit the tree.
        self.main_window.setTreeEditable('Android Manifest Tree', value=False)
        
        # On double-click, a window opens up, enabling the user to add a
        #  search rule (or return value) at that level.
        self.main_window.setTreeDoubleClickFunction(
            'Android Manifest Tree',
            self.fn_handle_manifest_tree_click
        )
        self.main_window.stopFrame()
    
    def fn_create_new_manifest_rule_subwindow(self):
        """Creates a small subwindow for specifying manifest search rules."""
        sw=self.main_window.startSubWindow('Create Manifest Rule', modal=True)
        sw.stopFunction = self.fn_hide_manifest_rule_window
        # Apply standard formatting.
        self.fn_apply_standard_window_formatting(500, 400)
        self.main_window.setSticky('new')  
        self.main_window.setStretch('COLUMN')
        self.main_window.setPadding([25, 15])          
        self.main_window.addLabel(
            'create_new_manifest_rule',
            'Create manifest rule'
        ).config(font='Tahoma 11 bold')
        self.main_window.setPadding([25, 5]) 
        # LOOKFOR.
        self.main_window.addCheckBox(
            'checkbox_add_manifest_lookfor'
        )
        self.main_window.setCheckBoxText(
            'checkbox_add_manifest_lookfor',
            'Perform checks at this level?'
        )
        self.main_window.setCheckBoxChangeFunction(
            'checkbox_add_manifest_lookfor',
            self.fn_handle_manifest_lookfor_checkbox_change
        )

        # Create an option box with the 4 possible types of LOOKFOR.
        lookfor_options = [
            'TAGEXISTS',
            'TAGNOTEXISTS',
            'TAGVALUEMATCH',
            'TAGVALUENOMATCH'
        ]
        self.fn_create_standard_optionbox(
            'Manifest Search Options',
            lookfor_options,
            label='Search rule: '
        )
        self.main_window.setOptionBoxChangeFunction(
            'Manifest Search Options',
            self.fn_on_manifest_option_select
        )
        
        # Create an option box and an entry field.
        # The option box will be populated dynamically.
        self.fn_create_standard_optionbox(
            'Manifest Search Tags',
            [],
            label='TAG:           '
        )
        self.fn_create_standard_entry(
            'label_manifest_search_tagvalue',
            label='VALUE:       '
        )

        # Hide all inputs unless the user actually clicks the checkbox.
        self.main_window.hideOptionBox('Manifest Search Options')
        self.main_window.hideOptionBox('Manifest Search Tags')
        self.main_window.hideEntry('label_manifest_search_tagvalue')        
        
        # RETURN.
        # Give the user the option to add returns.
        self.main_window.addLabel(
            'create_new_manifest_return',
            ''
        ).config(font='Tahoma 5')
        
        self.main_window.addCheckBox(
            'checkbox_add_manifest_returns'
        )
        self.main_window.setCheckBoxText(
            'checkbox_add_manifest_returns',
            'Return data at this level?'
        )
        self.main_window.setCheckBoxChangeFunction(
            'checkbox_add_manifest_returns',
            self.fn_handle_manifest_returns_checkbox_change
        )

        self.fn_create_standard_optionbox(
            'Manifest Return Tags',
            [],
            label='TAG:           '
        )
        self.fn_create_standard_entry(
            'entry_manifest_return_as',
            label='AS              ',
            tooltip='A unique identifier for the returned value.'
        )
        
        # Hide the widgets unless the user actually checks the checkbox.
        self.main_window.hideOptionBox('Manifest Return Tags')
        self.main_window.hideEntry('entry_manifest_return_as')
        
        # Create button to perform checks and finalise rule creation.
        self.fn_create_standard_frame('frame_create_manifest_rule_button')
        self.fn_create_standard_button(
            name='      Add Rule      ',
            title='Add Rule',
            func=self.fn_add_manifest_rule,
            row=0,
            column=0
        )
        self.main_window.addLabel(
            'manifest_rule_padding',
            '',
            row=0,
            column=1
        )
        # Also create a button to exit the window.
        self.fn_create_standard_button(
            title='Cancel Rule Creation',
            func=self.fn_hide_manifest_rule_window,
            row=0,
            column=2
        )
        self.main_window.stopFrame()
        
        # Create a status label. This is where any errors will be displayed.
        self.fn_create_standard_status_label('label_manifest_rule_status')
        
        # Finished creating the subwindow.
        self.main_window.stopSubWindow()
    
    def fn_create_new_template_stack_frame_code(self):
        """Creates a frame to create the CODEPARAMS section of template."""
        self.fn_create_standard_frame('frame_new_template_stack_code')
        self.main_window.setSticky('new')
        self.main_window.setStretch('COLUMN')
        self.main_window.addLabel(
            'label_code_settings',
            'Code analysis settings'
        ).config(
            bg=self.colour_main_background,
            fg=self.colour_main_foreground,
            anchor='w'
        )
        
        # Padding
        self.main_window.addLabel(
            'label_code_padding0',
            ''
        )
        
        # Search.
        self.fn_create_standard_button(
            title='Code Search Parameters',
            func=self.fn_show_code_search_rule_subwindow
        )
        # Padding
        self.main_window.addLabel(
            'label_code_padding1',
            ''
        )
        self.fn_create_standard_button(
            title='Code Trace Parameters',
            func=self.fn_show_code_trace_rule_subwindow
        )
        
        self.main_window.stopFrame()
    
    def fn_create_code_search_subwindow(self):
        """Creates a frame to create the CODE->SEARCH section of template."""
        sw=self.main_window.startSubWindow(
            'Create Code Search Rule',
            modal=True
        )
        sw.stopFunction = self.fn_hide_code_search_rule_window
        # Apply standard formatting.
        self.fn_apply_standard_window_formatting(500, 400)
        self.main_window.setSticky('new')  
        self.main_window.setStretch('COLUMN')
        self.main_window.setPadding([25, 15])          
        self.main_window.addLabel(
            'create_code_search_rule',
            'Create code search rule'
        ).config(font='Tahoma 11 bold')
        self.main_window.setPadding([25, 5]) 
        
        # Create an option box with the 6 possible types of SEARCH.
        search_options = [
            'SEARCHFORMETHOD',
            'SEARCHFORCALLTOMETHOD',
            'SEARCHFORCLASS',
            'SEARCHFORCALLTOCLASS',
            'SEARCHFORSTRING',
            'SEARCHFORCALLTOSTRING'
        ]
        self.fn_create_standard_optionbox(
            'Search Options',
            search_options,
            label='Search Type:      '
        )
        # Set a default value.
        self.main_window.setOptionBox(
            'Search Options',
            1
        )
        self.main_window.setOptionBoxChangeFunction(
            'Search Options',
            self.fn_on_code_search_option_select
        )

        self.fn_create_standard_entry(
            'entry_code_search_classmethodstring',
            label='Search Term:      ',
            tooltip='The class/method/string to search for.'
        )

        # We want a label, a qualifier and a search location.
        # First create a container.
        self.fn_create_standard_frame(
            'new_template_search_location'
        )
        self.main_window.setPadding([(0, 5), 5])
        self.main_window.setSticky('w')
        self.fn_create_standard_label(
            'label_search_location',
            'Search Location:',
            row=0,
            column=0
        )
        self.fn_create_standard_optionbox(
            'Code Search Location',
            ['<class>', '<method>'],
            row=0,
            column=1
        )
        self.main_window.setOptionBoxWidth(
            'Code Search Location',
            7
        )
        self.main_window.setPadding([0, 5])
        self.main_window.setSticky('news')
        self.fn_create_standard_entry(
            'entry_code_search_location',
            row=0,
            column=2,
            tooltip='A specific class/method within which to search. '
                    + 'Use the button on the right if you want to specify '
                    + 'a previously returned value.'
        )
        self.main_window.setEntryWidth(
            'entry_code_search_location',
            32
        )
        self.fn_create_standard_returns_button(
            title='button_show_returns_search',
            row=0,
            column=3,
            func=self.fn_set_search_listener_and_show_returns
        )
        
        self.main_window.stopFrame()

        # Remove padding.
        self.main_window.setPadding([25,0])

        # Reset padding.
        self.main_window.setPadding([25,5])
        
        # RETURN.
        # Give the user the option to add returns.
        self.main_window.addLabel(
            'create_code_search_return',
            ''
        ).config(font='Tahoma 5')
        
        self.main_window.addCheckBox(
            'checkbox_add_code_search_returns'
        )
        self.main_window.setCheckBoxText(
            'checkbox_add_code_search_returns',
            'Return data at this level?'
        )
        self.main_window.setCheckBoxChangeFunction(
            'checkbox_add_code_search_returns',
            self.fn_handle_code_search_returns_checkbox_change
        )

        self.fn_create_standard_optionbox(
            'Code Search Returns',
            ['<class>', '<method>'],
            label='Return:       '
        )
        self.fn_create_standard_entry(
            'label_code_search_return_as',
            label='AS:            ',
            tooltip='A unique identifier for the returned value.'
        )

        # Hide the widgets unless the user actually checks the checkbox.
        self.main_window.hideOptionBox('Code Search Returns')
        self.main_window.hideEntry('label_code_search_return_as')

        # Create button to perform checks and finalise rule creation.
        self.fn_create_standard_frame('frame_create_code_search_rule_button')
        self.fn_create_standard_button(
            name='      Add Rule      ',
            title='Add Code Search Rule',
            func=self.fn_add_code_search_rule,
            row=0,
            column=0
        )
        self.main_window.addLabel(
            'code_search_rule_padding',
            '',
            row=0,
            column=1
        )
        # Also create a button to exit the window.
        self.fn_create_standard_button(
            name='Cancel Rule Creation',
            title='Cancel Code Search Rule Creation',
            func=self.fn_hide_code_search_rule_window,
            row=0,
            column=2
        )
        self.main_window.stopFrame()
        
        self.fn_create_standard_status_label(
            'status_label_code_search_return_as'
        )

        # Finished creating the subwindow.
        self.main_window.stopSubWindow()
    
    def fn_create_code_trace_subwindow(self):
        """Creates a frame to create the CODE->TRACE section of template."""
        sw=self.main_window.startSubWindow(
            'Create Code Trace Rule',
            modal=True
        )
        sw.stopFunction = self.fn_hide_code_trace_rule_window
        # Apply standard formatting.
        self.fn_apply_standard_window_formatting(500, 400)
        self.main_window.setSticky('new')  
        self.main_window.setStretch('COLUMN')
        self.main_window.setPadding([25, 15])          
        self.main_window.addLabel(
            'create_code_trace_rule',
            'Create code trace rule'
        ).config(font='Tahoma 11 bold')
        self.main_window.setPadding([25, 5])
        
        # TRACEFROM
        # We want a label, a qualifier and a tracefrom location.
        # First create a container.
        self.fn_create_standard_frame(
            'new_template_tracefrom'
        )
        self.main_window.setPadding([(0, 5), 0])
        self.main_window.setSticky('w')
        self.fn_create_standard_label(
            'label_tracefrom',
            'Trace from:                 ',
            row=0,
            column=0
        )
        self.fn_create_standard_optionbox(
            'Trace From',
            ['', '<class>', '<method>'],
            row=0,
            column=1
        )
        self.main_window.setOptionBoxWidth(
            'Trace From',
            7
        )
        self.main_window.setPadding([0, 0])
        self.main_window.setSticky('news')
        self.fn_create_standard_entry(
            'entry_code_tracefrom',
            row=0,
            column=2,
            tooltip='The method or class to trace from. '
                    + 'Use the button on the right if you want to specify '
                    + 'a previously returned value.'
        )
        self.main_window.setEntryWidth(
            'entry_code_tracefrom',
            26
        )

        self.fn_create_standard_returns_button(
            title='button_show_returns_tracefrom',
            row=0,
            column=3,
            func=self.fn_set_tracefrom_listener_and_show_returns
        )
        self.main_window.stopFrame()
        
        # TRACETO
        # We want a label, a qualifier and a traceto location.
        # First create a container.
        self.fn_create_standard_frame(
            'new_template_traceto'
        )
        self.main_window.setPadding([(0, 5), 0])
        self.main_window.setSticky('w')
        self.fn_create_standard_label(
            'label_traceto',
            'Trace to:                     ',
            row=0,
            column=0
        )
        self.fn_create_standard_optionbox(
            'Trace To',
            ['', '<class>', '<method>'],
            row=0,
            column=1
        )
        self.main_window.setOptionBoxWidth(
            'Trace To',
            7
        )
        self.main_window.setPadding([0, 0])
        self.main_window.setSticky('news')
        self.fn_create_standard_entry(
            'entry_code_traceto',
            row=0,
            column=2,
            tooltip='The method or class to trace to. '
                    + 'Use the button on the right if you want to specify '
                    + 'a previously returned value.'
        )
        self.main_window.setEntryWidth(
            'entry_code_traceto',
            26
        )

        self.fn_create_standard_returns_button(
            title='button_show_returns_traceto',
            row=0,
            column=3,
            func=self.fn_set_traceto_listener_and_show_returns
        )
        self.main_window.stopFrame()

        # Add a trace direction option.
        self.fn_create_standard_optionbox(
            'optionbox_tracedirection',
            ['FORWARD', 'REVERSE'],
            label='Trace direction:             '
        )
        
        # Add a trace length option.
        self.fn_create_standard_entry(
            'optionbox_tracelength',
            entry_type='numeric',
            label='Max trace chain length: ',
            tooltip='Limit the trace length to reduce the complexity '
                    + 'of the output graph and to reduce analysis time.'
        )
        
        # Remove padding.
        self.main_window.setPadding([25,0])

        # Reset padding.
        self.main_window.setPadding([25,5])
        
        # RETURN.
        # Give the user the option to add returns.
        self.main_window.addLabel(
            'create_code_trace_return',
            ''
        )
        
        self.main_window.addCheckBox(
            'checkbox_add_code_trace_returns'
        )
        self.main_window.setCheckBoxText(
            'checkbox_add_code_trace_returns',
            'Return data at this level?'
        )
        self.main_window.setCheckBoxChangeFunction(
            'checkbox_add_code_trace_returns',
            self.fn_handle_code_trace_returns_checkbox_change
        )

        self.fn_create_standard_entry(
            'label_code_trace_return_as',
            label = 'Return <tracepath> AS @tracepath_',
            tooltip='A unique identifier for the trace path.'
        )

        # Hide the widgets unless the user actually checks the checkbox.
        self.main_window.hideEntry('label_code_trace_return_as')

        # Create button to perform checks and finalise rule creation.
        self.fn_create_standard_frame('frame_create_code_trace_rule_button')
        self.fn_create_standard_button(
            name='      Add Rule      ',
            title='Add Code Trace Rule',
            func=self.fn_add_code_trace_rule,
            row=0,
            column=0
        )
        self.main_window.addLabel(
            'code_trace_rule_padding',
            '',
            row=0,
            column=1
        )
        # Also create a button to exit the window.
        self.fn_create_standard_button(
            name='Cancel Rule Creation',
            title='Cancel Code Trace Rule Creation',
            func=self.fn_hide_code_trace_rule_window,
            row=0,
            column=2
        )
        self.main_window.stopFrame()
        
        self.fn_create_standard_status_label(
            'status_label_code_trace_return_as'
        )
        
        # Finished creating the subwindow.
        self.main_window.stopSubWindow()
        
    def fn_create_new_template_stack_frame_graph(self):
        self.fn_create_standard_frame('Create Graphing Rules')
        self.main_window.setSticky('new')
        self.main_window.setStretch('COLUMN')
        self.main_window.addLabel(
            'label_graph_settings',
            'Graph settings'
        ).config(
            bg=self.colour_main_background,
            fg=self.colour_main_foreground,
            anchor='w'
        )
        
        self.main_window.addEmptyLabel('padding_graph').config(font='Tahoma 5')
        self.fn_create_standard_optionbox(
           'entry_element_to_graph',
           [],
           label = 'Element to graph:  '
        )
        self.fn_update_graph_subwindow()
        
        self.main_window.addEmptyLabel('padding_graph2').config(font='Tahoma 5')
        self.main_window.addLabel(
            'label_graph_components',
            'Details to display on node'
        ).config(anchor='w')
        self.fn_create_standard_entry(
            'entry_components',
            tooltip='This can be <self>, which would return the value as-is. '
                    + 'Or it can be a combination of'
                    + ' one or more of <class>, <method>, <desc>.\n\nExample: '
                    + '<method>-<class> would display the method part '
                    + 'followed by a hyphen and then the class part.'
        )
        
        self.main_window.addEmptyLabel(
            'padding_graph3'
        ).config(font='Tahoma 5')
        self.main_window.addLabel(
            'label_graph_attributes',
            'List of attributes to graph in the form "name:value".\n'
            + 'Separate multiple entries using a comma.'
        ).config(anchor='w')
        self.fn_create_standard_entry('entry_graph_attributes')
        
        self.main_window.addEmptyLabel('padding_graph4').config(font='Tahoma 5')
        self.main_window.addLabel(
            'label_graph_labels',
            'List of labels to graph.\nSeparate multiple entries using a comma.'
        ).config(anchor='w')
        self.fn_create_standard_entry('entry_graph_labels')
        
        self.fn_create_standard_status_label('graph_status_label')
        self.main_window.stopFrame()

    def fn_create_new_template_stack_frame_confirm(self):
        self.fn_create_standard_frame('Confirmation Frame')
        self.main_window.setSticky('new')
        self.main_window.setStretch('COLUMN')
        self.main_window.addLabel(
            'label_template_confirmation',
            'Confirm Template Creation'
        ).config(
            bg=self.colour_main_background,
            fg=self.colour_main_foreground,
            anchor='w'
        )
        
        self.main_window.addEmptyLabel('padding_confirmation').config(font='Tahoma 8')
        self.main_window.addLabel(
            'label_confirmation',
            'Double-check the generated template in the right pane\n'
            + 'and click GENERATE to save.'
        ).config(anchor='w')
        
        self.fn_create_standard_button(
            'GENERATE',
            func=self.fn_generate_new_template
        )
        
        self.main_window.stopFrame()
    
    def fn_create_new_template_right_frame(self):
        """Creates the right pane for new template creation."""
        # Create frame.
        self.fn_create_standard_frame('frame_new_templates_right', 0, 1)
        self.main_window.setSticky('new')
        self.main_window.setStretch('COLUMN')
        self.main_window.addLabel(
            'label_new_template_content',
            'Template Content'
        ).config(
            fg=self.colour_main_foreground,
            anchor='e'
        )
        
        # Create a textarea box with the template content.
        self.fn_create_standard_textarea('New Template Content')
        self.main_window.setTextAreaHeight('New Template Content', 21)
        self.main_window.setTextAreaWidth('New Template Content', 70)
        self.main_window.setTextAreaPadding('New Template Content', [15, 15])
        self.main_window.setTextAreaFont(
            'New Template Content',
            size=8,
            family=self.default_font_family
        )
        
        # Finished creating frame.
        self.main_window.stopFrame()
    
    def fn_create_template_help_frame(self):
        # Create the frame.
        self.fn_create_standard_frame('frame_template_help', 4, 0)
        self.main_window.setSticky('news')
        self.main_window.setStretch('COLUMN')
        
        self.main_window.addLabel(
            'label_template_help_header',
            'About Jandroid Templates'
        ).config(
            fg=self.colour_main_foreground,
            anchor='w'
        )
        
        self.fn_create_standard_textarea('Template Help', text=None)
        self.main_window.setTextAreaHeight('Template Help', 18)
        #self.main_window.setTextAreaWidth('Template Help', 81)
        self.main_window.setTextAreaPadding('Template Help', [5, 15])
        self.main_window.setTextAreaFont(
            'Template Help',
            size=10,
            family=self.default_font_family
        )
        template_file_path = os.path.join(
            self.path_current_dir,
            'files',
            'template_help.txt'
        )
        template_help_text = open(template_file_path).read().strip()
        self.main_window.setTextArea(
            'Template Help',
            template_help_text,
            end=False
        )
        self.main_window.textAreaApplyFontRange(
            'Template Help',
            'UNDERLINE',
            1.0,
            2.0
        )
        self.main_window.textAreaApplyFontRange(
            'Template Help',
            'BOLD',
            1.0,
            2.0
        )
        self.main_window.textAreaApplyFontRange(
            'Template Help',
            'BOLD',
            3.0,
            4.0
        )
        self.main_window.textAreaApplyFontRange(
            'Template Help',
            'BOLD',
            6.0,
            7.0
        )
        self.main_window.textAreaApplyFontRange(
            'Template Help',
            'ITALIC',
            8.0,
            9.0
        )
        self.main_window.textAreaApplyFontRange(
            'Template Help',
            'BOLD',
            10.0,
            11.0
        )
        self.main_window.stopFrame()
    
    def fn_create_statusbar(self):
        """Create a small status bar at the bottom of the main window."""
        self.main_window.addStatusbar(fields=1)
        self.main_window.statusFont = 9

    def fn_create_log_window(self):
        """Create a window to display the stdout of the Jandroid process."""
        # Create subwindow.
        self.main_window.startSubWindow('Jandroid Analysis Log')
        self.fn_apply_standard_window_formatting(width=350, height=600)
        self.main_window.setSticky('new')
        self.main_window.setPadding([25, 10])
        self.main_window.addLabel(
            'label_console_logger',
            'Console Logger'
        ).config(font='Tahoma 11 bold')        
        
        # Add scrolled text area to display the stdout text.        
        self.fn_create_standard_textarea('Log File', text=None)
        self.main_window.setTextAreaHeight('Log File', 30)
        self.main_window.setTextAreaWidth('Log File', 330)
        self.main_window.setTextAreaPadding('Log File', [10, 10])
        self.main_window.setTextAreaFont('Log File', size=8, family='Tahoma')
        
        # Provide an option to save the log.
        self.fn_create_standard_button(
            title='Save Log',
            func=self.fn_save_log_file
        )
        
        self.fn_create_standard_status_label('status_save')
        # Done creating subwindow.
        self.main_window.stopSubWindow()
    
    def fn_create_returns_window(self):
        """Create a window to display a list of the current returns list."""
        # Create subwindow.
        sw=self.main_window.startSubWindow('Current Returns', modal=True)
        sw.stopFunction = self.fn_hide_current_returns_subwindow
        self.fn_apply_standard_window_formatting(width=280, height=400)
        self.main_window.setSticky('new')
        self.main_window.setPadding([25, 10])
        self.main_window.addLabel(
            'label_current_returns',
            'Linked Items'
        ).config(font='Tahoma 11 bold')        
        
        return_values = self.fn_remove_tracepath_returns()
        self.fn_create_standard_listbox('Linkable Returns', return_values)
        self.main_window.setListBoxHeight('Linkable Returns', 19)
        self.main_window.setListBoxWidth('Linkable Returns', 260)
        self.main_window.setListBoxPadding('Linkable Returns', [10, 10])
        self.main_window.setListBoxChangeFunction(
            'Linkable Returns',
            self.fn_update_entry_with_return_value
        )
        
        # Done creating subwindow.
        self.main_window.stopSubWindow()
        
    def fn_create_returns_from_trace_window(self):
        """Create a window to display a list of the current returns list."""
        # Create subwindow.
        sw=self.main_window.startSubWindow('Current Returns for Trace', modal=True)
        sw.stopFunction = self.fn_hide_current_returns_for_trace_subwindow
        self.fn_apply_standard_window_formatting(width=280, height=400)
        self.main_window.setSticky('new')
        self.main_window.setPadding([25, 10])
        self.main_window.addLabel(
            'label_current_returns_for_trace',
            'Linked Items'
        ).config(font='Tahoma 11 bold')        
        
        return_values = self.fn_returns_for_trace()
        self.fn_create_standard_listbox('Linkable Returns for Trace', return_values)
        self.main_window.setListBoxHeight('Linkable Returns for Trace', 19)
        self.main_window.setListBoxWidth('Linkable Returns for Trace', 260)
        self.main_window.setListBoxPadding('Linkable Returns for Trace', [10, 10])
        self.main_window.setListBoxChangeFunction(
            'Linkable Returns for Trace',
            self.fn_update_entry_with_return_value
        )
        
        # Done creating subwindow.
        self.main_window.stopSubWindow()        
    
    """ =============== GUI component hide/show =============== """
    
    def fn_open_graph_in_browser(self):
        graph_file = os.path.join(
            self.path_base_dir,
            'output',
            'graph',
            'jandroid.html'
        )
        if os.path.isfile(graph_file):
            webbrowser.open_new(graph_file)
        else:
            self.main_window.errorBox(
               'message_no_graph_file',
               'Sorry, no graph file found.'               
            )
    
    def fn_show_advanced_config_subwindow(self):
        self.main_window.showSubWindow('Advanced Configuration')

    def fn_hide_advanced_config_subwindow(self):
        self.main_window.hideSubWindow('Advanced Configuration')    
    
    def fn_show_template_manager_subwindow(self):
        self.fn_reset_new_template_frame_stack()
        self.main_window.setRadioButton(
            'template_manager_radio_box_group',
            '               View Existing Templates               '
        )
        self.main_window.raiseFrame('frame_existing_templates_parent')
        self.main_window.showSubWindow('Template Manager')
        
    def fn_show_existing_templates_subwindow(self):
        self.main_window.raiseFrame('frame_existing_templates_parent')
        
    def fn_show_create_new_template_subwindow(self):
        self.main_window.raiseFrame('frame_new_template_parent')

    def fn_show_template_help(self):
        self.main_window.raiseFrame('frame_template_help')

    def fn_show_log_window(self):
        self.main_window.showSubWindow('Jandroid Analysis Log')
    
    def fn_show_manifest_rule_subwindow(self):
        self.main_window.showSubWindow('Create Manifest Rule')
    
    def fn_hide_manifest_rule_window(self):
        self.main_window.hideSubWindow('Create Manifest Rule')
        self.main_window.showSubWindow('Template Manager')
    
    def fn_show_code_search_rule_subwindow(self):
        self.fn_update_code_search_subwindow()
        self.main_window.showSubWindow('Create Code Search Rule')
        
    def fn_hide_code_search_rule_window(self):
        self.main_window.hideSubWindow('Create Code Search Rule')
        self.main_window.showSubWindow('Template Manager')
        
    def fn_show_code_trace_rule_subwindow(self):
        self.fn_update_code_trace_subwindow()
        self.main_window.showSubWindow('Create Code Trace Rule')
        
    def fn_hide_code_trace_rule_window(self):
        self.main_window.hideSubWindow('Create Code Trace Rule')
        self.main_window.showSubWindow('Template Manager')
        
    def fn_show_current_returns_subwindow(self):
        return_values = self.fn_remove_tracepath_returns()
        self.main_window.updateListBox('Linkable Returns', return_values)
        self.main_window.showSubWindow('Current Returns')

    def fn_hide_current_returns_subwindow(self):
        self.main_window.hideSubWindow(self.current_returns_window)
        if self.current_top_window != None:
            self.main_window.showSubWindow(self.current_top_window)
            self.current_top_window = None
        
    def fn_show_current_returns_for_trace_subwindow(self):
        return_values = self.fn_returns_for_trace()
        self.main_window.updateListBox(
            'Linkable Returns for Trace',
            return_values
        )
        self.main_window.showSubWindow('Current Returns for Trace')
        
    def fn_hide_current_returns_for_trace_subwindow(self):
        self.main_window.hideSubWindow('Current Returns for Trace')
        if self.current_top_window != None:
            self.main_window.showSubWindow(self.current_top_window)
            self.current_top_window = None
            
    def fn_show_current_returns_for_graph_subwindow(self):
        self.main_window.updateListBox(
            'Linkable Returns for Graph',
            self.current_returns
        )
        self.main_window.showSubWindow('Current Returns for Graph')
    
    def fn_hide_current_returns_for_graph_subwindow(self):
        self.main_window.hideSubWindow('Current Returns for Graph')
        if self.current_top_window != None:
            self.main_window.showSubWindow(self.current_top_window)
            self.current_top_window = None
        
        
    """ =============== Functional code =============== """
    
    def fn_check_python_version(self):
        """Checks the version of Python being used.
        
        :returns: boolean with a value of True if Python version is > 3.4, 
            False otherwise
        """
        # We require Python > v3.4
        if sys.version_info < (3, 4):
            return False
        return True
        
    def fn_show_menu_about_jandroid(self):
        """DIsplays a message about Jandroid."""
        about_message = 'Jandroid started out as Joern for Android... ' \
                        + 'but perhaps not to quite that scale. ' \
                        + 'The goal was a tool that could automatically ' \
                        + 'analyse Android apps to identify logic bugs.\n\n' \
                        + 'Essentially, Jandroid analyses apps and matches ' \
                        + 'them against templates, which look for certain ' \
                        + 'parameters or functionality. In the context ' \
                        + 'of logic bugs in Android apps, each template ' \
                        + 'corresponds to one logic bug, or one start/end ' \
                        + 'point. By testing a number of apps against ' \
                        + 'multiple bug templates and linking the bugs ' \
                        + 'together, we might be able to identify an '\
                        + 'exploit chain.'
        self.main_window.infoBox('About', about_message)

    def fn_on_platform_radiobutton_changed(self):
        """Raises frame based on the platform-selection radio button."""
        # Get the value of the radio button.
        radio_button_value = self.main_window.getRadioButton('platform_radio')
        
        # The radio buttons have capitalised values.
        # We use lower case for names.
        self.analysis_platform = radio_button_value.lower()
        
        # Raise the appropriate frame.
        self.main_window.raiseFrame(
            'platform_specific_frame_right_' 
            + self.analysis_platform
        )
        
    def fn_save_config_file(self):
        """Saves the configuration file after confirming with user."""
        # Get text from text area (holding the config file text).
        new_contents = self.main_window.getTextArea('Config File')
        
        # If the text area is all blank (or all newlines), then warn user.
        if new_contents.replace('\n', '').replace(' ', '') == '':
            bool_overwrite_config = self.main_window.yesNoBox(
                'Config Overwrite',
                'Are you sure you want to overwrite the existing config file '
                + 'with a blank file?',
                parent='Advanced Configuration'
            )
        # Even if not, ask the user.
        else:
            bool_overwrite_config = self.main_window.yesNoBox(
                'Config Save',
                'Are you sure you want to save your changes to the config '
                + 'file?',
                parent='Advanced Configuration'
            )
        
        # If the user says yes, then overwrite.
        if bool_overwrite_config == True:
            with open(self.config_file, 'w') as conf_file:
                conf_file.write(new_contents)

    def fn_handle_templatemanager_radio_box_change(self, radio_box):
        radio_box_selection = self.main_window.getRadioButton(radio_box)
        if (radio_box_selection == 
                '               View Existing Templates               '):
            self.fn_show_existing_templates_subwindow()
        elif (radio_box_selection == 
                '                 Create New Template                 '):
            self.fn_show_create_new_template_subwindow()
        else:
            self.fn_show_template_help()
        
    def fn_populate_existing_templates(self):
        """Populates a ListBox with existing templates."""
        # Enumerate templates.
        template_folder = os.path.join(
            self.path_base_dir,
            'templates',
            self.analysis_platform
        )
        list_of_template_files = [
            os.path.join(template_folder, name)
            for name in os.listdir(template_folder)
                if ((os.path.isfile(
                    os.path.join(template_folder, name)
                )) and (name.endswith('.template')))
        ]
        
        # Create a template object.
        self.template_object = {}
        # Populate the template object.
        for template_file in list_of_template_files:
            template_content = json.load(open(template_file))
            template_name = template_content['METADATA']['NAME']
            self.template_object[template_name] = open(template_file).read()
        
        # Update the list box with names of all the templates.
        all_template_names = []
        for template_item in self.template_object:
            all_template_names.append(template_item)
        self.main_window.updateListBox(
            'Available Templates',
            all_template_names
        )
        
        # Set an event listener for change events.
        self.main_window.setListBoxChangeFunction(
            'Available Templates',
            self.fn_populate_existing_template_content
        )
        
    def fn_populate_existing_template_content(self):
        """Populates an EntryBox with template content."""
        # Get the value of the listbox selection.
        listbox_selection = self.main_window.getListBox('Available Templates')

        # This function is triggered even when focus leaves the list box.
        # So handle instances where selection is an empty list.
        if listbox_selection == []:
            return
        if listbox_selection == None:
            return

        # The listbox contents are returned as a list. But because we have
        #  disabled multi-select, the list will always contain only one item.
        selected_template = listbox_selection[0]
        
        # Get the JSON content that we have stored in our template object.
        template_content = self.template_object[selected_template]
        self.main_window.clearTextArea('Template Content')
        self.main_window.setTextArea(
            'Template Content',
            text=template_content,
            end=False            
        )

    def fn_handle_template_creation_stack(self, btn):
        if btn == 'RESET':
            self.fn_reset_new_template_frame_stack()
            return
        curr_frame = self.main_window.getCurrentFrame('Template Creator')
        if curr_frame == 0:
            # We could only have pressed NEXT, as PREV is disabled.
            # So we needn't do any button checks.
            start_frame_checks = self.fn_perform_start_frame_checks()
            if start_frame_checks == True:
                if 'M' in self.template_creation_mode:
                    self.main_window.nextFrame('Template Creator')
                else:
                    self.fn_update_code_search_subwindow()
                    self.main_window.selectFrame('Template Creator', 2)
                self.main_window.enableButton('PREV')
        
        elif curr_frame == 1:
            #frame_1_checks = self.fn_perform_frame_1_checks()
            if btn == 'PREV':
                self.main_window.disableButton('PREV')
                self.main_window.prevFrame('Template Creator')
            elif btn == 'NEXT':
                if 'C' in self.template_creation_mode:
                    self.fn_update_code_search_subwindow()
                    self.main_window.nextFrame('Template Creator')
                else:
                    self.fn_update_graph_subwindow()
                    self.main_window.selectFrame('Template Creator', 3)
                
        elif curr_frame == 2:
            #frame_2_checks = self.fn_perform_frame_2_checks()
            if btn == 'NEXT':
                self.fn_update_graph_subwindow()
                self.main_window.nextFrame('Template Creator')
            elif btn == 'PREV':
                if 'M' in self.template_creation_mode:
                    self.main_window.prevFrame('Template Creator')
                else:
                    self.main_window.selectFrame('Template Creator', 0)
                    self.main_window.disableButton('PREV')
            
        elif curr_frame == 3:            
            if btn == 'NEXT':
                graph_frame_checks = self.fn_perform_graph_frame_checks()
                if graph_frame_checks == True:
                    self.main_window.disableButton('NEXT')
                    self.main_window.nextFrame('Template Creator')
            elif btn == 'PREV':
                if 'C' in self.template_creation_mode:
                    self.fn_update_code_search_subwindow()
                    self.main_window.prevFrame('Template Creator')
                else:
                    self.main_window.selectFrame('Template Creator', 1)
                
        elif curr_frame == 4:
            # The button could only have been PREV, so no need to do
            #  any checks.
            self.main_window.enableButton('NEXT')
            self.fn_update_graph_subwindow()
            self.main_window.prevFrame('Template Creator')

    #=========== Pertaining to new template creation: start frame ===========#
    def fn_perform_start_frame_checks(self):
        name_valid = self.fn_perform_template_name_validation()
        if name_valid == False:
            return False
        
        analysis_option = self.main_window.getOptionBox(
            'Template Options'
        )
        if analysis_option == 'Manifest search':
            self.template_creation_mode = 'M'
            if 'MANIFESTPARAMS' not in self.new_template_object:
                self.new_template_object['MANIFESTPARAMS'] = {}
                self.new_template_object['MANIFESTPARAMS']['SEARCHPATH'] = {}
            if 'CODEPARAMS' in self.new_template_object:
                del self.new_template_object['CODEPARAMS']
        elif analysis_option == 'Code search/trace':
            self.template_creation_mode = 'C'
            if 'CODEPARAMS' not in self.new_template_object:
                self.new_template_object['CODEPARAMS'] = {}
            if 'MANIFESTPARAMS' in self.new_template_object:
                del self.new_template_object['MANIFESTPARAMS']
        elif analysis_option == 'Manifest search & code search/trace':
            self.template_creation_mode = 'MC'
            if 'MANIFESTPARAMS' not in self.new_template_object:
                self.new_template_object['MANIFESTPARAMS'] = {}
                self.new_template_object['MANIFESTPARAMS']['SEARCHPATH'] = {}
            if 'CODEPARAMS' not in self.new_template_object:
                self.new_template_object['CODEPARAMS'] = {}
                
        self.main_window.clearTextArea('New Template Content')
        self.main_window.setTextArea(
            'New Template Content',
            json.dumps(self.new_template_object, indent=4)
        )
        return True
    
    def fn_perform_template_name_validation(self):
        new_bug_name = self.main_window.getEntry('Template Name')
        check_validity = self.fn_check_entry_validity(new_bug_name)
        if check_validity != True:
            self.fn_set_entry_invalid(
                'Template Name',
                'label_template_name_status',
                check_validity
            )
            return False
        else:
            self.fn_set_entry_valid(
                'Template Name',
                'label_template_name_status'
            )
        self.new_template_object['METADATA'] = {}
        self.new_template_object['METADATA']['NAME'] = new_bug_name
        return True
    
    #============= Pertaining to new template creation: manifest frame ===========#    
    def fn_handle_manifest_tree_click(self, tree_name, id):
        self.fn_reset_manifest_rule_window()
        self.current_manifest_tree_id = id
        selected_value = self.main_window.getTreeSelected(tree_name)
        # Clicking on expansion buttons also generates click events
        #  (although probably not double-click events). To eliminate
        #  None events, we return on None.
        if selected_value == None:
            return
        
        # Populate the option boxes.
        self.main_window.changeOptionBox(
            'Manifest Search Tags',
            self.manifest_tags[id]
        )
        self.main_window.changeOptionBox(
            'Manifest Return Tags',
            self.manifest_tags[id]
        )
        # If not None, show the rule creation subwindow.
        self.fn_show_manifest_rule_subwindow()
    
    def fn_on_manifest_option_select(self):
        selected_option = self.main_window.getOptionBox('Manifest Search Options')
        if selected_option in ['TAGVALUEMATCH', 'TAGVALUENOMATCH']:
            self.main_window.showEntry('label_manifest_search_tagvalue')
        else:
            self.main_window.hideEntry('label_manifest_search_tagvalue')
    
    def fn_handle_manifest_lookfor_checkbox_change(self):
        radio_box_selected = self.main_window.getCheckBox(
            'checkbox_add_manifest_lookfor'
        )
        if radio_box_selected == True:
            self.main_window.showOptionBox('Manifest Search Options')
            self.main_window.setOptionBox('Manifest Search Options', 0)
            self.main_window.showOptionBox('Manifest Search Tags')
        else:
            self.main_window.hideOptionBox('Manifest Search Options')
            self.main_window.hideOptionBox('Manifest Search Tags')
            self.main_window.hideEntry('label_manifest_search_tagvalue')
        
    def fn_handle_manifest_returns_checkbox_change(self):
        radio_box_selected = self.main_window.getCheckBox(
            'checkbox_add_manifest_returns'
        )
        if radio_box_selected == True:
            self.main_window.showOptionBox('Manifest Return Tags')
            self.main_window.showEntry('entry_manifest_return_as')
        else:
            self.main_window.hideOptionBox('Manifest Return Tags')
            self.main_window.hideEntry('entry_manifest_return_as')
    
    def fn_add_manifest_rule(self):        
        bool_get_lookfor = self.main_window.getCheckBox(
            'checkbox_add_manifest_lookfor'
        )
        bool_get_return = self.main_window.getCheckBox(
            'checkbox_add_manifest_returns'
        )
        if (bool_get_lookfor == False) and (bool_get_return == False):
            self.main_window.setLabel(
                'label_manifest_rule_status',
                'At least one of search or return must be specified.'
            )
            return

        if bool_get_lookfor == True:
            lookfor_ok = self.fn_perform_manifest_lookfor_validation()
        else:
            lookfor_ok = True

        if bool_get_return == True:
            return_ok = self.fn_perform_manifest_return_validation()
        else:
            return_ok = True

        if (lookfor_ok != True) or (return_ok != True):
            return
            
        # If basic validation succeeds, then get the params.
        if bool_get_lookfor == True:
            self.fn_get_manifest_lookfor_params()
        if bool_get_return == True:
            self.fn_get_manifest_return_params()
        self.main_window.clearTextArea('New Template Content')
        self.main_window.setTextArea(
            'New Template Content',
            json.dumps(self.new_template_object, indent=4)
        )
        self.fn_hide_manifest_rule_window()

    def fn_perform_manifest_lookfor_validation(self):
        lookfor_type = self.main_window.getOptionBox('Manifest Search Options')
        lookfor_value = self.fn_cleaned_text(
            self.main_window.getEntry('label_manifest_search_tagvalue')
        )
        if lookfor_type in ['TAGVALUEMATCH', 'TAGVALUENOMATCH']:
            if lookfor_value == '':
                self.fn_set_entry_invalid(
                    'label_manifest_search_tagvalue',
                    'label_manifest_rule_status',
                    'A value must be specified to match against.'
                )
            else:
                self.fn_set_entry_valid(
                    'label_manifest_search_tagvalue',
                    'label_manifest_rule_status'
                )
                return True
        else:
            return True
                
    def fn_perform_manifest_return_validation(self):
        return_as = self.fn_cleaned_text(
            self.main_window.getEntry('entry_manifest_return_as')
        )
        check_validity = self.fn_check_return_validity(return_as)
        if check_validity != True:
            self.fn_set_entry_invalid(
                'entry_manifest_return_as',
                'label_manifest_rule_status',
                check_validity
            )
        else:
            self.fn_set_entry_valid(
                'entry_manifest_return_as',
                'label_manifest_rule_status',
            )
            return True

    def fn_get_manifest_lookfor_params(self):
        lookfor_type = self.main_window.getOptionBox('Manifest Search Options')
        lookfor_tag = self.main_window.getOptionBox('Manifest Search Tags')     
        lookfor_value = self.fn_cleaned_text(
            self.main_window.getEntry('label_manifest_search_tagvalue')
        )
        if lookfor_type in ['TAGVALUEMATCH', 'TAGVALUENOMATCH']:
            lookfor_text = lookfor_tag + '=' + lookfor_value
        else:
            lookfor_text = lookfor_tag
        current_level = self.new_template_object['MANIFESTPARAMS']['SEARCHPATH']
        split_manifest_path = self.current_manifest_tree_id.split('->')
        for index, split_manifest_path_item in enumerate(split_manifest_path):
            if split_manifest_path_item not in current_level:
                current_level[split_manifest_path_item] = {}
                current_level = current_level[split_manifest_path_item]
            else:
                current_level = current_level[split_manifest_path_item]
            if index == (len(split_manifest_path) - 1):
                # We are at the end of the split path. So we can add the tags.
                if 'LOOKFOR' not in current_level:
                    current_level['LOOKFOR'] = {}
                if lookfor_type not in current_level['LOOKFOR']:
                    current_level['LOOKFOR'][lookfor_type] = []
                if lookfor_text not in current_level['LOOKFOR'][lookfor_type]:
                    current_level['LOOKFOR'][lookfor_type].append(lookfor_text)
    
    def fn_get_manifest_return_params(self):
        return_tag = self.main_window.getOptionBox('Manifest Return Tags')
        return_tag = '<smali>:' + return_tag
        return_as = self.fn_cleaned_text(
            self.main_window.getEntry('entry_manifest_return_as')
        )
        return_as = '@' + return_as
        if return_as not in self.current_returns:
            self.current_returns.append(return_as)
        return_text = return_tag + ' AS ' + return_as
        current_level = self.new_template_object['MANIFESTPARAMS']['SEARCHPATH']
        split_manifest_path = self.current_manifest_tree_id.split('->')
        for index, split_manifest_path_item in enumerate(split_manifest_path):
            if split_manifest_path_item not in current_level:
                current_level[split_manifest_path_item] = {}
                current_level = current_level[split_manifest_path_item]
            else:
                current_level = current_level[split_manifest_path_item]
            if index == (len(split_manifest_path) - 1):
                # We are at the end of the split path. So we can add the tags.
                if 'RETURN' not in current_level:
                    current_level['RETURN'] = []
                if return_text not in current_level['RETURN']:
                    current_level['RETURN'].append(return_text)

    #============= Pertaining to new template creation: code frame ===========#
    def fn_update_code_search_subwindow(self):
        self.fn_reset_new_template_left_frame_code_search()
        self.main_window.changeAutoEntry(
            'entry_code_search_location',
            self.fn_remove_tracepath_returns()
        )

    def fn_on_code_search_option_select(self):
        selected_option = self.main_window.getOptionBox('Search Options')
        no_additional_options = [
            'SEARCHFORCLASS',
            'SEARCHFORMETHOD',
            'SEARCHFORSTRING'
        ]
        if selected_option in no_additional_options:
            self.main_window.hideLabel('label_search_location')
            self.main_window.hideOptionBox('Code Search Location')
            self.main_window.hideEntry('entry_code_search_location')
            self.main_window.hideOptionBox('Code Search Returns')
            self.main_window.hideEntry('label_code_search_return_as')
            self.main_window.hideCheckBox('checkbox_add_code_search_returns')
        else:
            self.main_window.showLabel('label_search_location')
            self.main_window.showOptionBox('Code Search Location')
            self.main_window.showEntry('entry_code_search_location')

    def fn_handle_code_search_returns_checkbox_change(self):
        bool_return_selected = \
            self.main_window.getCheckBox('checkbox_add_code_search_returns')
        if bool_return_selected == True:
            self.main_window.showOptionBox('Code Search Returns')
            self.main_window.clearEntry('label_code_search_return_as')
            self.main_window.showEntry('label_code_search_return_as')
        else:
            self.main_window.hideOptionBox('Code Search Returns')
            self.main_window.hideEntry('label_code_search_return_as')
    
    def fn_add_code_search_rule(self):
        search_type = self.main_window.getOptionBox('Search Options')
        search_value = self.fn_cleaned_text(
            self.main_window.getEntry('entry_code_search_classmethodstring')
        )
        if search_value == '':
            self.fn_set_entry_invalid(
                'entry_code_search_classmethodstring',
                'status_label_code_search_return_as',
                'Search value cannot be blank.'
            )
            return
            
        search_location_type = self.main_window.getOptionBox(
            'Code Search Location'
        )
        search_location = self.fn_cleaned_text(
            self.main_window.getEntry('entry_code_search_location')
        )
        if search_location != '':
            if len(search_location) < 2:
                self.fn_set_entry_invalid(
                    'entry_code_search_location',
                    'status_label_code_search_return_as',
                    'Search location cannot be single-character value.'
                )
                return
            if search_location[0] == '@':
                if search_location not in self.current_returns:
                    self.fn_set_entry_invalid(
                        'entry_code_search_location',
                        'status_label_code_search_return_as',
                        'Search location linked item not found.'
                    )
                    return

        return_value_check = [
            'SEARCHFORCALLTOMETHOD',
            'SEARCHFORCALLTOCLASS',
            'SEARCHFORCALLTOSTRING'
        ]
        
        bool_get_return = self.main_window.getCheckBox(
            'checkbox_add_code_search_returns'
        )
        return_value = self.main_window.getOptionBox('Code Search Returns')
        return_as = self.fn_cleaned_text(
            self.main_window.getEntry('label_code_search_return_as')
        )
        
        if search_type in return_value_check:
            if bool_get_return == True:
                check_validity = self.fn_check_return_validity(return_as)
                if check_validity != True:
                    self.fn_set_entry_invalid(
                        'label_code_search_return_as',
                        'status_label_code_search_return_as',
                        check_validity
                    )
                    return
                return_as = '@' + return_as
                self.current_returns.append(return_as)
                    
                self.fn_set_entry_valid(
                    'label_code_search_return_as',
                    'status_label_code_search_return_as'
                )
        
        if 'SEARCH' not in self.new_template_object['CODEPARAMS']:
            self.new_template_object['CODEPARAMS']['SEARCH'] = []
        search_object = {}
        if search_type not in search_object:
            search_object[search_type] = {}
        # Extract out the CLASS, METHOD, STRING
        search_granular_type = \
            search_type.replace('SEARCHFOR','').replace('CALLTO','')
        if search_granular_type not in search_object[search_type]:
            search_object[search_type][search_granular_type] = search_value
        # Add location, return if search type is SEARCHFORCALLTOx
        if search_type in return_value_check:
            if search_location != '':
                search_object[search_type]['SEARCHLOCATION'] = \
                    search_location_type + ':' + search_location
            if bool_get_return == True:
                return_string = return_value + ' AS ' + return_as
                search_object[search_type]['RETURN'] = return_string
        
        search_template = self.new_template_object['CODEPARAMS']['SEARCH']
        if search_object not in search_template:
            search_template.append(search_object)
            
        self.main_window.clearTextArea('New Template Content')
        self.main_window.setTextArea(
            'New Template Content',
            json.dumps(self.new_template_object, indent=4)
        )
        
        self.fn_hide_code_search_rule_window()

    def fn_set_search_listener_and_show_returns(self):
        self.current_listener = 'entry_code_search_location'
        self.current_top_window = 'Create Code Search Rule'
        self.current_returns_window = 'Current Returns'
        self.fn_show_current_returns_subwindow()
    
    def fn_update_code_trace_subwindow(self):
        self.fn_reset_new_template_left_frame_code_trace()
        self.main_window.changeAutoEntry(
           'entry_code_tracefrom',
           self.fn_remove_tracepath_returns()
        )
        self.main_window.changeAutoEntry(
           'entry_code_traceto',
           self.fn_remove_tracepath_returns()
        )
        
    def fn_handle_code_trace_returns_checkbox_change(self):
        bool_return_selected = \
            self.main_window.getCheckBox('checkbox_add_code_trace_returns')
        if bool_return_selected == True:
            self.main_window.clearEntry('label_code_trace_return_as')
            self.main_window.showEntry('label_code_trace_return_as')
        else:
            self.main_window.hideEntry('label_code_trace_return_as')
    
    def fn_add_code_trace_rule(self):
        # Get TRACEFROM parameters.
        trace_from_type = self.main_window.getOptionBox(
            'Trace From'
        )
        if trace_from_type == None:
            trace_from_type = ''
        else:
            trace_from_type = trace_from_type + ':'
        trace_from = self.fn_cleaned_text(
            self.main_window.getEntry('entry_code_tracefrom')
        )
        if trace_from == '':
            self.fn_set_entry_invalid('entry_code_tracefrom')
            self.main_window.setLabel(
                'status_label_code_trace_return_as',
                INVALID_INPUT['len_blank']
            )
            return
        if trace_from[0] == '@':
            if trace_from.split('[')[0] not in self.current_returns:
                self.fn_set_entry_invalid(
                    'entry_code_tracefrom',
                    'status_label_code_trace_return_as',
                    'TRACEFROM linked item not found.'
                )
                return
            
        # Get TRACETO parameters.
        trace_to_type = self.main_window.getOptionBox(
            'Trace To'
        )
        if trace_to_type == None:
            trace_to_type = ''
        else:
            trace_to_type = trace_to_type + ':'
        trace_to = self.fn_cleaned_text(
            self.main_window.getEntry('entry_code_traceto')
        )
        if trace_to == '':
            self.fn_set_entry_invalid(
                'entry_code_traceto',
                'status_label_code_trace_return_as',
                INVALID_INPUT['len_blank']
            )
            return
        if trace_to[0] == '@':
            if trace_to.split('[')[0] not in self.current_returns:
                self.fn_set_entry_invalid(
                    'entry_code_traceto',
                    'status_label_code_trace_return_as',
                    'TRACETO linked item not found.'
                )
                return

        trace_direction = self.main_window.getOptionBox(
            'optionbox_tracedirection'
        )
        trace_chain_max_length = \
            self.main_window.getEntry('optionbox_tracelength')

        if 'TRACE' not in self.new_template_object['CODEPARAMS']:
            self.new_template_object['CODEPARAMS']['TRACE'] = []
        trace_object = {}
        trace_object['TRACEFROM'] = trace_from_type + trace_from
        trace_object['TRACETO'] = trace_to_type + trace_to
        trace_object['TRACEDIRECTION'] = trace_direction
        if ((trace_chain_max_length != '') and
            (trace_chain_max_length != None)):
            trace_object['TRACELENGTHMAX'] = int(trace_chain_max_length)
            
        # Returns.
        return_trace = self.main_window.getCheckBox(
            'checkbox_add_code_trace_returns'
        )
        if return_trace == True:
            return_as_raw = self.fn_cleaned_text(
                self.main_window.getEntry('label_code_trace_return_as')
            )
            return_as = '@tracepath_' + return_as_raw
            check_validity = self.fn_check_return_validity(return_as_raw)
            if check_validity != True:
                self.fn_set_entry_invalid(
                    'label_code_trace_return_as',
                    'status_label_code_trace_return_as',
                    check_validity
                )
                return
            
            # Is there any use in appending this to returns?
            self.current_returns.append(return_as)
            
            return_as_string = '<tracepath> AS ' + return_as
            if 'RETURN' not in trace_object:
                trace_object['RETURN'] = []
            trace_object['RETURN'].append(return_as_string)
        # Add the trace object to the new template object.
        if trace_object not in self.new_template_object['CODEPARAMS']['TRACE']:
            self.new_template_object['CODEPARAMS']['TRACE'].append(
                trace_object
            )
        
        self.main_window.clearTextArea('New Template Content')
        self.main_window.setTextArea(
            'New Template Content',
            json.dumps(self.new_template_object, indent=4)
        )
        self.fn_hide_code_trace_rule_window()
    
    def fn_set_tracefrom_listener_and_show_returns(self):
        self.current_listener = 'entry_code_tracefrom'
        self.current_top_window = 'Create Code Trace Rule'
        self.current_returns_window = 'Current Returns for Trace'
        self.fn_show_current_returns_for_trace_subwindow()
        
    def fn_set_traceto_listener_and_show_returns(self):
        self.current_listener = 'entry_code_traceto'
        self.current_top_window = 'Create Code Trace Rule'
        self.current_returns_window = 'Current Returns for Trace'
        self.fn_show_current_returns_for_trace_subwindow()
        
    def fn_update_entry_with_return_value(self, widget_name):
        if self.current_listener == None:
            return
        selected_value = self.main_window.getListBox(widget_name)
        if selected_value == []:
            return
        selected_value = selected_value[0]
        self.main_window.setEntry(self.current_listener, selected_value)
        self.current_listener = None
        self.fn_hide_current_returns_subwindow()
        
    def fn_perform_graph_frame_checks(self):
        selected_option = self.main_window.getOptionBox(
            'entry_element_to_graph'
        )
        if selected_option == None:
            return True
        if selected_option.replace(' ', '') == '':
            return True
        if selected_option[0].replace(' ', '') == '-':
            return True
        graphable_element = self.fn_cleaned_text(
            selected_option
        )
        if graphable_element == '':
            return True
        graph_format = self.fn_cleaned_text(
            self.main_window.getEntry('entry_components')
        )
        if graph_format == '':
            self.fn_set_entry_invalid(
                'entry_components',
                'graph_status_label',
                'Specify a pattern for the primary node attribute.'
            )
            return False
        
        # Get the node identifier.
        config = configparser.ConfigParser()
        config.read(self.config_file)
        node_identifier = 'nodename'
        if config.has_section('NEO4J'):
            if config.has_option('NEO4J', 'NODE_IDENTIFIER'):
                node_identifier = (
                    config['NEO4J']['NODE_IDENTIFIER']
                )
        
        # Start the graph string with the info we have.
        formatted_graph_string = graphable_element \
                                 + ' WITH ' \
                                 + graph_format \
                                 + ' AS attribute=' \
                                 + node_identifier
        
        # Add attributes.
        graph_attributes = self.fn_cleaned_text(
            self.main_window.getEntry('entry_graph_attributes')
        )
        create_graphable_attribute_string = self.fn_process_attributes(
            graph_attributes
        )
        if create_graphable_attribute_string == False:
            return False
        self.main_window.setLabel(
            'graph_status_label',
            ''
        )
        formatted_graph_string = formatted_graph_string \
                                 + create_graphable_attribute_string
        graph_labels = self.fn_cleaned_text(
            self.main_window.getEntry('entry_graph_labels')
        )
        create_graphable_label_string = self.fn_process_labels(
            graph_labels
        )
        formatted_graph_string = formatted_graph_string \
                                 + create_graphable_label_string
        self.new_template_object['GRAPH'] = formatted_graph_string
        self.main_window.clearTextArea('New Template Content')
        self.main_window.setTextArea(
            'New Template Content',
            json.dumps(self.new_template_object, indent=4)
        )
        return True
    
    def fn_process_attributes(self, attribute_namevalues):
        if attribute_namevalues == '':
            return ''
        formatted_attribute_values = ''
        attribute_namevalue_list = attribute_namevalues.split(',')
        attribute_namevalue_list = list(set(attribute_namevalue_list))
        for attribute_namevalue in attribute_namevalue_list:
            attribute_namevalue = self.fn_cleaned_text(attribute_namevalue)
            if attribute_namevalue == '':
                continue
            split_pair = attribute_namevalue.split(':')
            if (len(split_pair) != 2):
                self.fn_set_entry_invalid(
                    'entry_graph_attributes',
                    'graph_status_label',
                    'Attributes must be specified as "attribute_name:value".'
                )
                return False
            elif (split_pair[1].replace(' ', '') == ''):
                self.fn_set_entry_invalid(
                    'entry_graph_attributes',
                    'graph_status_label',
                    'Attributes must be specified as "attribute_name:value".'
                )
                return False
            
            # Reset the label if everything's ok.
            self.main_window.setLabel(
                'graph_status_label',
                ''
            )
                
            formatted_attribute_values = formatted_attribute_values + ',' \
                                         + split_pair[1] \
                                         + ' AS attribute=' \
                                         +  split_pair[0]
        return formatted_attribute_values
    
    def fn_process_labels(self, labels):
        if labels == '':
            return ''
        formatted_label_values = ''
        label_list = labels.split(',')
        for label in label_list:
            label = self.fn_cleaned_text(label)
            if label == '':
                continue
            formatted_label_values = formatted_label_values + ',' \
                                     + label \
                                     + ' AS label'
        return formatted_label_values
            
    def fn_update_graph_subwindow(self):
        if self.current_returns == []:
            graphables = ['- Nothing to graph -', '@app']
        else:
            graphables = ['- Do not graph -', '@app']
            graphables = graphables + self.current_returns
        self.main_window.changeOptionBox(
            'entry_element_to_graph',
            graphables,
            index=0,
            callFunction=False
        )    
        
    def fn_generate_new_template(self):
        template_file_name = ''
        default_name = self.new_template_object['METADATA']['NAME'] \
                       + '.template'
        save_directory = os.path.join(
            self.path_base_dir,
            'templates',
            self.analysis_platform
        )
        template_file_name = self.main_window.saveBox(
                title='Save template file',
                fileName=default_name,
                fileExt=".template",
                dirName=save_directory,
                parent='Template Manager'
            ).replace(' ', '')
        if template_file_name == '':
            return
        template_content = self.main_window.getTextArea('New Template Content')
        with open(template_file_name, 'w') as f:
            f.write(template_content)
    
    """ =============== Component reset =============== """
    def fn_reset_new_template_frame_stack(self):
        # Reset buttons and variables.
        self.main_window.firstFrame('Template Creator')
        self.main_window.disableButton('PREV')
        self.main_window.enableButton('NEXT')
        self.fn_reset_new_template_variables()
        # Reset individual frames.
        self.fn_reset_new_template_left_frame_start()
        self.fn_reset_new_template_left_frame_manifest()
        self.fn_reset_new_template_left_frame_code()
        self.fn_reset_new_template_left_frame_graph()
        self.fn_reset_new_template_right_frame()

    def fn_reset_new_template_variables(self):
        self.new_template_object = {}
        self.current_returns = []
        self.template_creation_mode = 'M'
        
    def fn_reset_new_template_left_frame_start(self):
        self.main_window.setEntry('Template Name', text='')
        self.fn_reset_new_template_name_entry_to_wait()
    
    def fn_reset_new_template_name_entry_to_wait(self):
        self.fn_set_entry_valid(
            'Template Name',
            'label_template_name_status'
        )
        
    def fn_reset_new_template_left_frame_manifest(self):
        self.current_manifest_tree_id = 'manifest'
        self.fn_reset_manifest_rule_window()        
    
    def fn_reset_manifest_rule_window(self):
        self.main_window.setCheckBox(
            'checkbox_add_manifest_lookfor',
            ticked=False
        )
        self.main_window.setCheckBox(
            'checkbox_add_manifest_returns',
            ticked=False
        )
        self.main_window.clearEntry('entry_manifest_return_as')
        self.main_window.clearEntry('label_manifest_search_tagvalue')
        self.fn_set_entry_valid('entry_manifest_return_as')
        self.fn_set_entry_valid('label_manifest_search_tagvalue')
    
    def fn_reset_new_template_left_frame_code(self):
        self.fn_reset_new_template_left_frame_code_search()
        self.fn_reset_new_template_left_frame_code_trace()
    
    def fn_reset_new_template_left_frame_code_search(self):
        self.main_window.clearEntry('entry_code_search_classmethodstring')
        self.main_window.clearEntry('label_code_search_return_as')
        self.main_window.clearEntry('entry_code_search_location')
        self.main_window.setOptionBox(
            'Search Options',
            1
        )
        self.main_window.setCheckBox(
            'checkbox_add_code_search_returns',
            ticked=False
        )
    
    def fn_reset_new_template_left_frame_code_trace(self):
        self.main_window.setOptionBox(
            'Trace From',
            0
        )
        self.main_window.setOptionBox(
            'Trace To',
            0
        )
        self.main_window.setOptionBox(
            'optionbox_tracedirection',
            1
        )
        self.main_window.setOptionBox(
            'optionbox_tracedirection',
            1
        )
        self.main_window.clearEntry('optionbox_tracelength')
        self.main_window.setCheckBox(
            'checkbox_add_code_trace_returns',
            ticked=False
        )
        self.main_window.clearEntry('entry_code_tracefrom')
        self.main_window.clearEntry('entry_code_traceto')
        self.main_window.clearEntry('label_code_trace_return_as')
        self.main_window.setLabel(
            'status_label_code_trace_return_as',
            ''
        )

    def fn_reset_new_template_left_frame_graph(self):
        self.main_window.setOptionBox(
            'entry_element_to_graph',
            0,
            callFunction=False
        )
        self.main_window.clearEntry('entry_components')
        self.main_window.clearEntry('entry_graph_attributes')
        self.main_window.clearEntry('entry_graph_labels')
        
    def fn_reset_new_template_right_frame(self):
        self.main_window.clearTextArea('New Template Content')
    
    """ ================== Utility functions =================== """
    
    def fn_cleaned_text(self, text):
        output_text = text.replace('\n', '').replace(' ', '')
        return output_text
    
    def fn_check_entry_validity(self, text):
        if text == None:
            return INVALID_INPUT['len_blank']
        if text.replace('\n', '').replace(' ', '') == '':
            return INVALID_INPUT['len_blank']
        if not len(text) <= MAX_FIELD_LIMIT:
            return INVALID_INPUT['len_long']
        if not re.match("^[A-Za-z0-9_]*$", text):
            return INVALID_INPUT['invalid_chars']
        return True
        
    def fn_check_return_validity(self, text):
        general_validity = self.fn_check_entry_validity(text)
        if general_validity != True:
            return general_validity
        text = '@' + text
        if text in self.current_returns:
            return INVALID_INPUT['return_exists']
        if text in KEYWORDS:
            return INVALID_INPUT['reserved']
        return True
    
    def fn_remove_tracepath_returns(self):
        new_returns = []
        for return_item in self.current_returns:
            # We don't want tracepaths because they can't be used as links.
            if '@tracepath' not in return_item:
                new_returns.append(return_item)
        return new_returns
        
    def fn_returns_for_trace(self):
        new_returns = []
        for return_item in self.current_returns:
            # We don't want tracepaths because they can't be used as links.
            if '@tracepath' in return_item:
                continue
            new_returns.append(return_item + '[]')
            new_returns.append(return_item + '[<class>]')
            new_returns.append(return_item + '[<method>]')
        return new_returns

        
    """ =============== Main analysis start/stop =============== """
    def fn_start_stop_analysis(self):
        """Determines what to do based on whether an analysis is running."""
        # If an analysis is running, then the user has selected to stop
        #  the analysis. Ask for confirmation and then call the termination
        #  function.
        if self.bool_analysis_in_progress == True:
            bool_kill_process = self.main_window.yesNoBox(
                'Kill running processes?',
                'Analysis instances are running. '
                + 'Are you sure you want to terminate them?'
            )
            if bool_kill_process == True:
                # We don't want the main GUI to close.
                self.bool_preserve_main_process = True
                self.fn_terminate_analysis()
        # If an analysis is not running, then start the analysis.
        else:
            # Keep the user updated via the status bar.
            self.main_window.setStatusbar('Beginning analysis')
            # Clear the log window.
            self.main_window.clearTextArea('Log File')
            # If we started the analysis in the main process, then the GUI
            #  would freeze until the analysis terminates. Because analyses
            #  can run for quite a long time, we start the analysis in a 
            #  separate thread.
            # Note that, if we didn't want to get the output of the analysis
            #  (that is, the stdout or the returncode), then we wouldn't need
            #  the thread. But then, we also wouldn't need subprocesses, as
            #  we could instantiate the Jandroid class and call its methods
            #  directly.
            self.main_window.thread(self.start_jandroid)
            
    def start_jandroid(self):
        """Creates process options and starts Jandroid in a subprocess."""
        # Set values indicating that an analysis has started.
        self.fn_set_start_analysis_options()

        # Get all required arguments.
        self.fn_get_all_jandroid_arguments()

        # Create a list of arguments to be passed to the subprocess.
        jandroid_main_file = os.path.join(
            self.path_base_dir,
            'src',
            'jandroid.py'
        )
        jandroid_args = ['python', jandroid_main_file]
        
        if self.bool_generate_graph == True:
            jandroid_args.append('-g')
            jandroid_args.append(self.graph_type)
            
        if self.pull_source != None:
            jandroid_args.append('-e')
            jandroid_args.append(self.pull_source)
        
        if self.path_app_folder != None:
            jandroid_args.append('-f')
            jandroid_args.append(self.path_app_folder)

        # Reset the log.
        self.main_window.clearTextArea('Log File')
        
        # Update the status bar.
        self.main_window.setStatusbar('Analysing...')
        
        # Start the subprocess, redirecting stdout and stderr to Pipe.
        PIPE = subprocess.PIPE
        self.jandroid_process = subprocess.Popen(
            jandroid_args,
            stdout=PIPE,
            stderr=PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Get each line of stdout and update the text area
        #  in the Log Subwindow.
        for stdout_line in self.jandroid_process.stdout:
            try:
                self.main_window.queueFunction(
                    self.main_window.setTextArea,
                    'Log File',
                    stdout_line
                )
            except Exception as e:
                pass
        self.jandroid_process.stdout.close()
        
        # Wait for the process to end and get the returncode.
        self.jandroid_process.wait()
        returncode = self.jandroid_process.returncode
        # Update the status bar based on the returncode.
        if returncode == 1:
            self.main_window.setStatusbar(
                'An error occurred. '
                + 'Please check the log file for details.'
            )
        if returncode == 0:
            self.main_window.setStatusbar(
                'Analysis completed.'
            )
            if ((self.bool_generate_graph == True) and 
                    (self.graph_type in ['visjs', 'both'])):
                self.main_window.enableButton('Open Custom Graph')
            
        # Reset values.
        self.fn_set_stop_analysis_options()
        # Resetting this is important, as otherwise, the GUI wouldn't be
        #  closeable using ctrl+c on the console.
        self.bool_preserve_main_process = False

    def fn_set_start_analysis_options(self):
        """Sets variables and disables widgets when an analysis in running."""
        # Set a variable to indicate that an analysis is in progress.
        # This will be used when handling window close events.
        self.bool_analysis_in_progress = True
        
        # Change the "Start Analysis" button's text to "Stop Analysis".
        self.main_window.setButton('Start Analysis', 'Stop Analysis')
        
        # Disable buttons and check boxes.
        self.main_window.disableRadioButton('platform_radio')
        self.main_window.disableRadioButton('platform_pull_src')
        self.main_window.disableCheckBox('Output to Neo4j?')
        self.main_window.disableCheckBox('Output to custom graph?')
        self.main_window.disableButton('Open Custom Graph')
        self.main_window.disableButton('Advanced Configuration')
        self.main_window.disableButton('Template Manager')
        self.main_window.setEntryState('app_directory', 'disabled')
        
    def fn_set_stop_analysis_options(self):
        """Resets variables and enables widgets when an analysis stops."""
        # Set a variable to indicate that an analysis is not in progress.
        # This will be used when handling window close events.
        self.bool_analysis_in_progress = False
        
        # Change the "Start Analysis" button's text back to "Start Analysis".
        self.main_window.setButton('Start Analysis', 'Start Analysis')
        
        # Re-enable buttons and checkboxes.
        self.main_window.enableRadioButton('platform_radio')
        self.main_window.enableRadioButton('platform_pull_src')
        self.main_window.enableCheckBox('Output to Neo4j?')
        self.main_window.enableCheckBox('Output to custom graph?')
        self.main_window.enableButton('Advanced Configuration')
        self.main_window.enableButton('Template Manager')
        self.main_window.setEntryState('app_directory', 'normal')
        
    def fn_get_all_jandroid_arguments(self):
        """Get all arguments required to run Jandroid from widgets."""
        # We already know the analysis platform. 
        # No need to do anything more for it.
        
        # Get the pull option.
        pull_radio_button_value = self.main_window.getRadioButton(
            'platform_pull_src'
        )
        # We have to get the index of the source text, and then use it as an
        #  index into a list of formated values.
        # List of display values.
        display_vals = \
            self.available_platforms[self.analysis_platform][STR_PULL_TEXT]
        # Index of selection within display values.
        pull_radio_button_index = display_vals.index(pull_radio_button_value)
        # List of formatted values.
        formatted_vals = \
            self.available_platforms[self.analysis_platform][STR_PULL_SRC]
        # Formatted value at the same index position as the
        #  selected display value.
        self.pull_source = formatted_vals[pull_radio_button_index]

        # Get app directory.
        self.path_app_folder = self.main_window.getEntry('app_directory')
        
        # Get graph related data.
        bool_neo4j_graph_gen = \
            self.main_window.getCheckBox('Output to Neo4j?')
        bool_custom_graph_gen = \
            self.main_window.getCheckBox('Output to custom graph?')
        if ((bool_neo4j_graph_gen == True) or (bool_custom_graph_gen == True)):
            self.bool_generate_graph = True
        if ((bool_neo4j_graph_gen == True) and (bool_custom_graph_gen == True)):
            self.graph_type = 'both'
        elif (bool_neo4j_graph_gen == True):
            self.graph_type = 'neo4j'
        elif (bool_custom_graph_gen == True):
            self.graph_type = 'visjs'
            
            
    def fn_save_log_file(self, log_contents):
        """Saves the log file to user-specified location."""        
        log_file_name = 'log.txt'
        # Display a save window, for the user to choose a location
        #  and specify a name for the file.
        # If the log file name is left blank, don't allow the save.
        log_file_name = self.main_window.saveBox(
                title='Save log file',
                fileName='log.txt',
                fileExt=".txt",
                parent='Jandroid Analysis Log'
            ).replace(' ', '')
        if log_file_name == '':
            return
        
        # Get the contents of the text area in the Log subwindow,
        #  and write out to file.
        log_contents = self.main_window.getTextArea('Log File')
        with open(log_file_name, 'w') as log_file:
            log_file.write(log_contents)
            
    def fn_handle_main_window_close(self, signalnum=None, stackframe=None):
        """Handles the closing of the GUI under different circumstances.
        
        This is quite a tricky function because of the CTRL_C_EVENT hack used 
        to kill subprocesses on WIndows. There are 3 different scenarios 
        to take into consideration:
            1. Ctrl+C from console:
                * Child processes must be killed.
                * GUI must be closed.
            2. GUI window close button:
                * Child processes must be killed.
                * GUI must be closed.
            3. Unintended consequence of using ctrl+c to kill subprocess:
                * Child processes must be killed.
                * GUI must NOT be closed.
        
        :param signalnum: the numeric representation of the signal that was 
            received. Will be None when this function is called via appJar's 
            setStopFunction method.
        :param stackframe: the stack frame that is returned (we don't use 
            this for anything)
        :returns: boolean with value True if the GUI is to be closed, and 
            False otherwise.
        """
        if signalnum == 2:
            # If ctrl+c was issued programmatically, it would have been to
            #  kill a subprocess, and we would want to preserve the main
            #  window, so we return False.
            if self.bool_preserve_main_process == True:            
                return False
            # If ctrl+c was issued through the console, then kill child
            #  processes and exit. Don't forget, returning False won't work.
            #  Must use sys.exit()
            else:
                self.fn_terminate_analysis()
                sys.exit(0)
        
        # If the GUI window is closed, then (if child processes are running)
        #  ask for confirmation before terminating them.
        # We treat closure of the GUI window differently to ctrl+c via the
        #  console, because in general, ctrl+c is issued when we want to kill
        #  the process.
        if self.bool_analysis_in_progress == True:
            bool_confirm_kill_process = self.main_window.yesNoBox(
                'Confirm process termination',
                'Processes still running. '
                + 'Are you sure you want to terminate?'
            )
            if bool_confirm_kill_process == True:
                self.fn_terminate_analysis()
                return True
            else:
                return False
        else:
            return True
        
    def fn_terminate_analysis(self):
        """Sends the SIGTERM or ctrl+c event, to terminate child processes.
        
        This function sends the ctrl+c event to the child process if the 
        execution platform is Windows, and the SIGTERM signal on others.
        
        Unfortunately, this has the unintended side-effect of sending ctrl+c 
        to the main process as well, which is handled elsewhere.
        """
        if self.jandroid_process == None:
            return
        # Windows 
        if self.execution_platform == 'windows':
            self.jandroid_process.send_signal(signal.CTRL_C_EVENT)
        # Other platforms.
        else:
            self.jandroid_process.send_signal(signal.SIGTERM)
        self.fn_set_stop_analysis_options()
        self.main_window.setStatusbar('Analysis terminated')
    
    """ ===== Functions to print out a banner, just to prevent boredom ===== """
    
    def fn_load_banner(self):
        try:
            banner_folder = os.path.join(
                self.path_current_dir,
                'resources',
                'banner'
            )
            
            num_banners = len(
                [name for name in os.listdir(banner_folder) 
                if os.path.isfile(os.path.join(banner_folder, name))]
            )
            
            random_file = 'banner' \
                          + str(random.randint(0, num_banners-1)) \
                          + '.txt'
            banner_file = os.path.join(
                banner_folder,
                random_file
            )
            with open(banner_file) as f:
                self.banner_lines = f.read().splitlines()
        except:
            self.banner_lines = []
            
        # Start a counter.
        self.banner_counter = 0

    def fn_print_banner_line(self):
        if self.banner_off == True:
            return
        if self.banner_lines == []:
            return
        if self.banner_counter >= len(self.banner_lines):
            return
        print(Fore.CYAN, self.banner_lines[self.banner_counter])
        self.banner_counter += 1
        
    
if __name__ == '__main__':
    JandroidGui().main()
