import os
import re
import sys
import copy
import json
import logging
import configparser
from androguard.misc import *
from androguard.core import *
from analysis_utils import AnalysisUtils
from common import Conversions, JandroidException

TRACE_FORWARD = 'FORWARD'
TRACE_REVERSE = 'REVERSE'

STOP_CONDITION_TRUE = 'True'
STOP_CONDITION_FALSE = 'False'
STOP_CONDITION_MAYBE = 'Maybe'


class CodeTraceAdvanced:
    """Advanced code tracing."""
    
    def __init__(self, base_dir):
        """Sets paths and initialises variables.
        
        :param a: androguard.core.bytecodes.apk.APK object
        :param d: array of androguard.core.bytecodes.dvm.DalvikVMFormat objects
        :param dx: androguard.core.analysis.analysis.Analysis object
        :param base_dir: string indicating script base path
        """
        # Set paths.
        self.path_base_dir = base_dir

        # Initialise special case object.
        self.special_case_object_list_reverse = {
            'doInBackground': {
                'Landroid/os/AsyncTask;': [
                    'execute([Ljava/lang/Object;)Landroid/os/AsyncTask;', 
                    'execute(Ljava/lang/Runnable;)'
                ]
            }
        }
        self.special_case_object_list_forward = {
            'execute([Ljava/lang/Object;)Landroid/os/AsyncTask;': 'doInBackground',
            'execute(Ljava/lang/Runnable;)V': 'doInBackground'
        }
                                    
        # Store returns.
        self.current_returns = []
        
        self.stop_condition = STOP_CONDITION_FALSE

    def fn_reset(self):
        self.androguard_apk_obj = None
        self.androguard_d_array = None
        self.androguard_dx = None
        self.inst_analysis_utils = None
        self.all_annotations = None
        
    def fn_start_adv_trace(self, a, d, dx, code_trace_template, links,
                           direction=TRACE_REVERSE, max_trace_length=25):
        """Traces within code based on a trace template.
        
        :param code_trace_template: dictionary object corresponding to the 
            trace part of a bug template
        :param links: dictionary object containing linked items
        :param direction: string indicating direction to trace
        :param max_trace_length: integer indicating maximum length for 
            trace chains
        :returns: list containing boolean value indicating whether the trace 
            was satisfied, and a dictionary object of updated links
        """
        logging.debug('Performing advanced code trace.')
        # Androguard variables for this APK.
        self.androguard_apk_obj = a
        self.androguard_d_array = d
        self.androguard_dx = dx
        
        # Start up utility helper.
        self.inst_analysis_utils = AnalysisUtils(
            self.path_base_dir,
            self.androguard_apk_obj,
            self.androguard_d_array,
            self.androguard_dx
        )
        self.all_annotations = \
            self.inst_analysis_utils.fn_get_all_annotations()
        self.fn_get_jsinterface_classes_methods()
        
        # Linked elements from checking previous parts of the template.
        self.current_links = links
        
        self.trace_direction = direction
        
        self.trace_length_max = max_trace_length
        
        # Keep track of trace chains (to be converted to RETURN items).
        self.output_chains = []
        
        bool_satisfied = False
        
        self.fn_enumerate_trace_source_sinks(code_trace_template)
        for trace_from_item in self.trace_from_main_list:
            for trace_to_item in self.trace_to_main_list:
                bool_single_trace_satisfied = self.fn_trace_through_code(
                    trace_from_item,
                    trace_to_item
                )
                if bool_single_trace_satisfied == True:
                    bool_satisfied = True
        if bool_satisfied == True:
            if 'RETURN' in code_trace_template:
                self.fn_analyse_returns(code_trace_template)
                
        # Process returns as links.
        if bool_satisfied == True:
            self.current_links = \
                self.inst_analysis_utils.fn_convert_returns_to_links(
                    self.current_returns,
                    self.current_links
                )
                
        self.fn_reset()
        
        # Return the outcome and the links, to be used by next code segment.
        return [bool_satisfied, self.output_chains]
    
    def fn_trace_through_code(self, trace_from, trace_to):
        """Calls methods to parse arguments and starts trace handler.
        
        :param trace_from: string indicating start point(s) for trace
        :param trace_to: string indicating end point(s) for trace
        :returns: boolean indicating whether at least one path was identified
            between the start and end points
        """
        # Get trace types.
        [self.from_class_method, trace_from_string] = \
            self.fn_get_trace_type(trace_from)
        [self.to_class_method, trace_to_string] = \
            self.fn_get_trace_type(trace_to)
        # Get any linked items.
        trace_from_list = self.fn_get_trace_items(
            trace_from_string,
            self.from_class_method
        )
        trace_to_list = self.fn_get_trace_items(
            trace_to_string,
            self.to_class_method
        )
        if ((trace_from_list == []) or (trace_to_list == [])):
            logging.debug('Either TraceFrom or TraceTo evaluated to None.')
            return False
        self.trace_to_list = trace_to_list
        return self.fn_trace_handler(trace_from_list)
    
    def fn_trace_handler(self, trace_from_list):
        """Starts the trace process and outputs the result.
        
        :param trace_from_list: list containing possible start points
            for trace
        :returns: boolean indicating whether at least one path was identified
            between the start and end points
        """
        for trace_from in trace_from_list:
            self.checked_methods = set()
            self.checked_traceto_instructions = set()
            # Set a stop condition.
            self.stop_condition = STOP_CONDITION_FALSE
            # Start the forward or reverse tracers, based on template.
            if self.trace_direction == TRACE_REVERSE:
                self.fn_trace_reverse(
                    trace_from,
                    trace_from,
                    self.trace_from_argindex,
                    self.from_class_method
                )
            else:
                self.fn_trace_forward(
                    trace_from,
                    trace_from,
                    self.from_class_method
                )
        # If the output chain list is not empty, it means at least one path
        #  between the start and end points was identified.
        if self.output_chains != []:
            return True
        else:
            return False
    
    def fn_trace_forward(self, trace_from, chain, class_or_method=None):
        """Performs forward tracing.
        
        :param trace_from: string indicating starting point for trace
        :param chain: string containing comma-separated "chain links"
        :param class_or_method: either "<class>" or "<method">
        """
        # Get class/method/desc parts.
        [class_part, method_part, desc_part] = \
            self.fn_determine_class_method_desc(
                trace_from,
                class_or_method
            )

        # Include subclasses.
        all_classes = \
            self.inst_analysis_utils.fn_find_subclasses(class_part)
        all_classes.append(class_part)
        
        for one_class in all_classes:
            combined_method_string = one_class
            if '.' not in method_part:
                combined_method_string = combined_method_string \
                                         + '->' \
                                         + method_part
                if '.' not in desc_part:
                    combined_method_string = combined_method_string \
                                             + desc_part
            method_check_string = 'e' + combined_method_string
            if method_check_string in self.checked_methods:
                continue
            self.checked_methods.add(method_check_string)
            
            # If the trace to type doesn't care about arguments or results 
            #  (i.e., just a class or method),
            #  then perform a stop condition check.
            if ((self.trace_to_type != 'RESULTOF') and 
                    (self.trace_to_type != 'ARGTO')):
                self.fn_check_generic_stop_condition(combined_method_string)
            if self.stop_condition == STOP_CONDITION_TRUE:
                self.output_chains.append(chain)
                self.stop_condition = False
                continue
            
            # Get starting points.
            starting_points = \
                self.inst_analysis_utils.fn_get_calls_to_method(
                    one_class,
                    method_part,
                    desc_part
                )
            for starting_point in starting_points:
                num_locals = self.fn_get_locals(starting_point)
                    
                index_reg = self.fn_identify_result_reg(
                    starting_point,
                    combined_method_string
                )
                if index_reg == []:
                    continue
                for tuple in index_reg:
                    v_reg_trace_output = self.fn_trace_v_forward(
                        starting_point,
                        tuple[0]+1,
                        tuple[1],
                        chain
                    )
                    if v_reg_trace_output == True:
                        self.output_chains.append(chain)
                        self.stop_condition = STOP_CONDITION_FALSE
                        continue
                    else:
                        continue
                
    def fn_trace_v_forward(self, method, index, register, chain):
        """Traces a register forward from a starting point within a method.
        
        :param method: Androguard EncodedMethod to trace through
        :param index: instruction index (integer) to start trace from
        :param register: integer value of register
        :param chain: string containing comma-separated "chain links"
        """
        instructions = list(method.get_instructions())
        num_instructions = len(instructions)
        num_locals = self.fn_get_locals(method)
        [c, m, d] = \
            self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                method
            )
        method_string = c + '->' + m + d
        search_string = method_string + ':' + str(index) + ':' + str(register)
        method_check_string = 'i' + search_string + str(index) + str(register)
        if method_check_string in self.checked_methods:
            return
        self.checked_methods.add(method_check_string)
        new_chain = chain + ',' + method_string
        for i in range(index, num_instructions):
            instruction = instructions[i]
            opcode = instruction.get_op_value()
            operands = instruction.get_operands()
            for op_index, operand in enumerate(operands):
                if operand[0] != 0:
                    continue
                if (register != operand[1]):
                    continue
                # move
                if (opcode in 
                        [0x01, 0x02, 0x03, 0x04, 0x05, 
                         0x06, 0x07, 0x08, 0x09]):
                    # If the current register (the register of interest) 
                    #  is in position 0, that means its value has been 
                    #  overwritten. Stop tracing.
                    if op_index == 0:
                        return
                    # If the current register is in position 1, then its value has been
                    #  copied to another register. We should trace that register as well.
                    if op_index == 1:
                        self.fn_trace_v_forward(
                            method,
                            i+1,
                            operands[0][1],
                            chain
                        )
                # move-result.
                elif (opcode in [0x0A, 0x0B, 0x0C]):
                    return
                # constant
                elif (opcode in 
                        [0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 
                         0x18, 0x19, 0x1A, 0x1B, 0x1C]):
                    return
                # aget
                elif (opcode in [0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A]):
                    if op_index == 0:
                        return
                    if op_index == 1:
                        self.fn_trace_v_forward(
                            method,
                            i+1,
                            operands[0][1],
                            chain
                        )
                # aput
                elif (opcode in [0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51]):
                    if op_index == 0:
                        self.fn_trace_v_forward(
                            method,
                            i+1,
                            operands[0][1],
                            chain
                        )
                    if op_index == 1:
                        return
                # iget
                elif (opcode in [0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58]):
                    if op_index == 0:
                        return
                # iput
                elif (opcode in [0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F]):
                    if op_index == 0:
                        iput_dest = operands[2][2]
                        self.fn_trace_field_forward(iput_dest, new_chain)
                # sget
                elif (opcode in [0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66]):
                    if op_index == 0:
                        return
                # sput
                elif (opcode in [0x67, 0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D]):
                    if op_index == 0:
                        sput_dest = operands[1][2]
                        self.fn_trace_field_forward(sput_dest, new_chain)
                # invoke
                elif (opcode in 
                        [0x6E, 0x6F, 0x70, 0x71, 0x72, 
                         0x74, 0x75, 0x76, 0x77, 0x78]):
                    final_operand = operands[-1][2]
                    if self.trace_to_type == 'ARGTO':                        
                        if final_operand in self.trace_to_list:
                            if self.trace_to_argindex != None:
                                if op_index == self.trace_to_argindex:
                                    self.output_chains.append(new_chain)
                                    return
                            else:
                                self.output_chains.append(new_chain)
                                return
                    # If the method is loadurl, then process further.
                    if ((final_operand.split('->')[1]).split('(')[0] 
                            == 'loadUrl'):
                        is_webview_instance = \
                            self.fn_check_webview_instance(
                                final_operand.split('->')[0]
                            )
                        if is_webview_instance == True:
                            jsinterface_classes = \
                                self.fn_check_jsbridge(
                                    final_operand.split('->')[0]
                                )
                            if jsinterface_classes != None:
                                jsinterface_methods = \
                                    self.fn_get_all_jsinterface_methods(
                                        jsinterface_classes
                                    )
                                for jsinterface_method in jsinterface_methods:
                                    self.fn_trace_p_forward(
                                        jsinterface_method,
                                        None,
                                        new_chain
                                    )
                    # Trace output.
                    if i != (num_instructions-1):
                        next_instr = instructions[i+1]
                        next_opcode = next_instr.get_op_value()
                        if next_opcode in [0x0A, 0x0B, 0x0C]:
                            move_result_operand = \
                                (next_instr.get_operands())[0][1]
                            self.fn_trace_v_forward(
                                method,
                                i+2,
                                move_result_operand,
                                chain
                            )
                    # If invoke-direct, then trace object.
                    if ((opcode in [0x70, 0x76]) and (op_index != 0)):
                        self.fn_trace_v_forward(
                            method,
                            i+1,
                            operands[0][1],
                            chain
                        )
                    # Trace within invoked method.
                    self.fn_trace_p_forward(
                        final_operand,
                        op_index,
                        new_chain
                    )
    
    def fn_check_webview_instance(self, class_name):
        """Checks if a class is a (subclass of) webview.
        
        :param class_name: string name of class
        :returns: boolean indicating whether the class is a subclass of webview
        """
        if class_name == 'Landroid/webkit/WebView;':
            return True
        superclasses = \
            self.inst_analysis_utils.fn_find_superclasses(class_name)
        for superclass in superclasses:
            if superclass == 'Landroid/webkit/WebView;':
                return True
        return False
    
    def fn_check_jsbridge(self, class_name):
        """Finds javascriptinterface methods for a given class.
        
        :param class_name: string name of class
        :returns: list of JavascriptInterface methods
        """
        string = class_name + '->addJavascriptInterface'
        if string in self.checked_methods:
            return
        self.checked_methods.add(string)
        all_methods = self.inst_analysis_utils.fn_get_calls_to_method(
            class_name,
            'addJavascriptInterface',
            '.'
        )
        output = []
        for method in all_methods:
            output.extend(self.fn_check_method_for_jsinterface_calls(method))
        return list(set(output))
            
    def fn_check_method_for_jsinterface_calls(self, method):
        """Checks method for presence of calls to JavascriptInterface class.
        
        :param method: Androguard EncodedMethod
        :returns: list of JavascriptInterface classes called by method
        """
        output = []
        for jsinterface_class in self.jsinterface_classes:
            # A very unscientific way of doing this.
            for instruction in list(method.get_instructions()):
                if (instruction.get_op_value() not in 
                        [0x6E, 0x6F, 0x70, 0x71, 0x72,
                        0x74, 0x75, 0x76, 0x77, 0x78]):
                    continue
                last_operand = instruction.get_operands()[-1][2]
                if jsinterface_class in last_operand:
                    output.append(jsinterface_class)
                    break
        return list(set(output))

    def fn_get_all_jsinterface_methods(self, jsinterface_classes):
        """Checks for all JavascriptInterface methods for JSinterface classes.
        
        :param jsinterface_classes: list of JavascriptInterface classes
        :returns: list of JavascriptInterface methods
        """
        output = set()
        for jsinterface_class in jsinterface_classes:
            for jsinterface_method in self.jsinterface_methods:
                if jsinterface_class in jsinterface_method:
                    output.add(jsinterface_method)
        return list(output)
    
    def fn_trace_p_forward(self, method_string, p_index, chain):
        """Traces registers used as operands to a method.
        
        :param method_string: string representation of method (smali)
        :param p_index: integer for specific operand index or None 
            for all operands
        :param chain: string containing comma-separated "chain links"
        """
        [class_part, method_part, desc_part] = \
            self.inst_analysis_utils.fn_get_class_method_desc_from_string(
                method_string
            )
        new_chain = chain + ',' + method_string
        all_methods = self.inst_analysis_utils.fn_get_methods(
            class_part,
            method_part,
            desc_part
        )
        for methodanalysis in all_methods:
            # Ignore external methods.
            if methodanalysis.is_external() == True:
                continue
            method = methodanalysis.get_method()
            # Ignore abstract methods. TODO: Get calls to.
            if method.get_code() == None:
                continue
            num_locals = self.fn_get_locals(method)
            total_registers = method.code.get_registers_size()
            if p_index != None:
                p_register = num_locals + p_index
                self.fn_trace_v_forward(method, 0, p_register, new_chain)
            else:
                for i in range(total_registers-num_locals):
                    p_register = num_locals + i
                    self.fn_trace_v_forward(method, 0, p_register, new_chain)
    
    def fn_trace_field_forward(self, field, chain):
        """Identifies "get" for field and traces the appropriate register.
        
        :param field: string representing field
        :param chain: string containing comma-separated "chain links"
        """
        field_components = field.split(' ')
        field = field_components[0] + ':' + field_components[1]
        field = field.replace('[','\[')
        all_fields = self.androguard_dx.find_fields(field)
        all_field_xref_to = []
        for field in all_fields:
            xref_to = field.get_xref_read()
            if xref_to[1] not in all_field_xref_to:
                all_field_xref_to.append(xref_to[1])
        for field_xref_to_method in all_field_xref_to:
            [c, m, d] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                    field_xref_to_method
                )
            field_xref_to_method_string = c + '->' + m + d
            new_chain = chain + ',' + field_xref_to_method_string
            num_locals = self.fn_get_locals(field_xref_to_method)
            instructions = list(field_xref_to_method.get_instructions())
            for index, instruction in enumerate(instructions):
                if (instruction.get_op_value() in 
                        [0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 
                        0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66]):
                    operands = instruction.get_operands()
                    last_operand = operands[-1][2]
                    if last_operand != field:
                        continue
                    field_source = operands[0][1]
                    self.fn_trace_forward(
                        field_xref_to_method_string,
                        new_chain
                    )
                    
    def fn_trace_reverse(self, trace_from, chain, position=0,
                         class_or_method=None):
        """Performs reverse tracing.
        
        :param trace_from: string indicating starting point for trace
        :param chain: string containing comma-separated "chain links"
        :param position: integer operand index
        :param class_or_method: either "<class>" or "<method">
        """
        # Get class/method/desc parts.
        [class_part, method_part, desc_part] = \
            self.fn_determine_class_method_desc(
                trace_from,
                class_or_method
            )
        # Include subclasses.
        all_classes = \
            self.inst_analysis_utils.fn_find_subclasses(class_part)
        all_classes.append(class_part)
        
        for one_class in all_classes:
            combined_method_string = one_class
            if '.' not in method_part:
                combined_method_string = \
                    combined_method_string + '->' + method_part
                if '.' not in desc_part:
                    combined_method_string = \
                        combined_method_string + desc_part
            method_check_string = 'e' + combined_method_string + ' ' + str(position)
            if method_check_string in self.checked_methods:
                continue
            self.checked_methods.add(method_check_string)
            # If the trace to type doesn't care about arguments or results 
            #  (i.e., just a class or method), 
            #  then perform a stop condition check.
            if ((self.trace_to_type != 'RESULTOF') and 
                    (self.trace_to_type != 'ARGTO')):
                self.fn_check_generic_stop_condition(combined_method_string)
            if self.stop_condition == STOP_CONDITION_TRUE:
                self.output_chains.append(chain)
                self.stop_condition = False
                continue
            
            # Check to see if the method is a JavaScript interface.
            # If it is, then the commands themselves may not be found within 
            #  the code. However, any webview that uses this must call the 
            #  <init> method of this class.
            if combined_method_string in self.all_annotations:
                if ('Landroid/webkit/JavascriptInterface;' in 
                        self.all_annotations[combined_method_string]):
                    method_part = '<init>'
                    desc_part = '.'
            # Get starting points.
            starting_points = \
                self.inst_analysis_utils.fn_get_calls_to_method(
                    one_class,
                    method_part,
                    desc_part
                )
            for starting_point in starting_points:
                [c, m, d] = \
                    self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                        starting_point
                    )
                starting_point_string = c + '->' + m + d
                method_check_string = 'r' \
                                      + starting_point_string \
                                      + ' ' \
                                      + combined_method_string
                if method_check_string in self.checked_methods:
                    continue
                self.checked_methods.add(method_check_string)
                num_locals = self.fn_get_locals(starting_point)
                if starting_point_string in self.all_annotations:
                    if ('Landroid/webkit/JavascriptInterface;' in 
                            self.all_annotations[starting_point_string]):
                        chain = chain + ',' + starting_point_string
                        starting_point_string = starting_point.get_class_name() \
                                                + '-><init>'
                        self.fn_trace_reverse(
                            starting_point_string,
                            chain + ',' + starting_point_string,
                            1
                        )
                        continue
                index_reg = self.fn_identify_instr_reg(
                    starting_point,
                    combined_method_string,
                    position
                )
                if index_reg == []:
                    continue
                for tuple in index_reg:
                    if tuple[1] < num_locals:
                        v_reg_trace_output = self.fn_trace_v_reverse(
                            starting_point,
                            tuple[0]-1,
                            tuple[1],
                            chain
                        )
                        if v_reg_trace_output == True:
                            self.output_chains.append(chain)
                            self.stop_condition = STOP_CONDITION_FALSE
                            continue
                        else:
                            continue
                    else:                        
                        self.fn_trace_reverse(
                            starting_point_string,
                            chain + ',' + starting_point_string,
                            tuple[1] - num_locals
                        )
    
    def fn_trace_v_reverse(self, method, index, register, chain):
        """Traces a register backward from a starting point within a method.
        
        :param method: Androguard EncodedMethod to trace through
        :param index: instruction index (integer) to start trace from
        :param register: integer value of register
        :param chain: string containing comma-separated "chain links"
        """
        instructions = list(method.get_instructions())
        num_instructions = len(instructions)
        num_locals = self.fn_get_locals(method)
        [c, m, d] = \
            self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                method
            )
        method_string = c + '->' + m + d
        new_chain = chain + ',' + method_string
        for i in range(index, 0, -1):
            instruction = instructions[i]
            opcode = instruction.get_op_value()
            operands = instruction.get_operands()
            for op_index, operand in enumerate(operands):
                # 0x00 is "register".
                if operand[0] != 0:
                    continue
                if (register != operand[1]):
                    continue
                # move
                if ((opcode in 
                        [0x01, 0x02, 0x03, 0x04, 0x05, 
                         0x06, 0x07, 0x08, 0x09]) and 
                        (op_index == 0)):
                    move_source = operands[1][1]
                    if move_source < num_locals:
                        self.fn_trace_v_reverse(
                            method,
                            i-1,
                            move_source,
                            chain
                        )
                    else:                        
                        self.fn_trace_reverse(
                            method_string,
                            new_chain,
                            move_source - num_locals
                        )
                    return
                # move-result.
                elif (opcode in [0x0A, 0x0B, 0x0C]):
                    previous_instruction = instructions[i-1]
                    # If move-result did not follow an invoke opcode,
                    #  then continue.
                    if (previous_instruction.get_op_value() not in 
                            [0x6E, 0x6F, 0x70, 0x71, 0x72,
                             0x74, 0x75, 0x76, 0x77, 0x78]):
                        continue
                    # See if previous instruction satisfies trace to condition.
                    if self.trace_to_type == 'RESULTOF':
                        self.fn_check_traceto_result(previous_instruction)
                        if self.stop_condition == STOP_CONDITION_TRUE:
                            return True
                    # Trace each register as well.
                    previous_operands = previous_instruction.get_operands()
                    for previous_operand in previous_operands:
                        if previous_operand[0] != 0:
                            continue
                        if previous_operand[1] < num_locals:
                            self.fn_trace_v_reverse(
                                method,
                                i-2,
                                previous_operand[1],
                                chain
                            )
                        else:
                            self.fn_trace_reverse(
                                method_string,
                                new_chain,
                                previous_operand[1] - num_locals
                            )
                    return
                # Constant declaration. This indicates a value change.
                # We aren't interested.
                elif (opcode in 
                        [0x12, 0x13, 0x14, 0x15, 0x16,
                         0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C]):
                    return
                # aget. We trace the source, and stop tracing the
                #  current register (because it would have had a different
                #  value prior to aget).
                elif ((opcode in 
                        [0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4A]) and 
                        (op_index==0)):
                    aget_source = operands[1][1]
                    if aget_source < num_locals:
                        self.fn_trace_v_reverse(
                            method,
                            i-1,
                            aget_source,
                            chain
                        )
                    else:                        
                        self.fn_trace_reverse(
                            method_string,
                            new_chain,
                            aget_source - num_locals
                        )
                    return
                # aput. 
                elif((opcode in 
                        [0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51]) and 
                        (op_index == 1)):
                    aput_source = operands[0][1]
                    if aput_source < num_locals:
                        self.fn_trace_v_reverse(
                            method,
                            i-1,
                            aput_source,
                            chain
                        )
                    else:
                        self.fn_trace_reverse(
                            method_string,
                            new_chain,
                            aput_source - num_locals
                        )
                    return
                # iget. We trace the source field, and stop tracing the
                #  current register (because it would have had a different
                #  value prior to aget).
                elif ((opcode in 
                        [0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58]) and 
                        (op_index==0)):
                    iget_source = operands[2][2]
                    self.fn_trace_field_reverse(iget_source, new_chain)
                    return
                # sget.
                elif ((opcode in 
                        [0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66]) and 
                        (op_index==0)):
                    sget_source = operands[1][2]
                    self.fn_trace_field_reverse(sget_source, new_chain)
                    return
                # invoke-<> method calls.
                # This should actually never come up, because ARGTO wouldn't be
                #  TRACETO in reverse tracing.
                elif (opcode in 
                        [0x6E, 0x6F, 0x70, 0x71, 0x72,
                         0x74, 0x75, 0x76, 0x77, 0x78]):
                    if self.trace_to_type == 'ARGTO':
                        self.fn_check_traceto_arg(instruction, op_index)
                        if self.stop_condition == STOP_CONDITION_TRUE:
                            return True
                    # If this is a class instantiation, then trace other args.
                    if op_index == 0:                        
                        if len(operands)<= 2:
                            continue
                        for x in range(1, len(operands)-1):
                            if operands[x][0] != 0:
                                continue
                            arg_operand = operands[x][1]
                            if arg_operand < num_locals:
                                self.fn_trace_v_reverse(
                                    method,
                                    i-1,
                                    arg_operand,
                                    chain
                                )
                            else:
                                
                                self.fn_trace_reverse(
                                    method_string,
                                    new_chain,
                                    arg_operand - num_locals
                                )
                    # Don't return here!
                
    def fn_trace_field_reverse(self, field, chain):
        """Identifies "put" for field and traces the appropriate register.
        
        :param field: string representing field
        :param chain: string containing comma-separated "chain links"
        """
        field_components = field.split(' ')
        field = field_components[0] + ':' + field_components[1]
        field = field.replace('[','\[')
        all_fields = self.androguard_dx.find_fields(field)
        all_field_xref_from = []
        for field in all_fields:
            xref_from = field.get_xref_write()
            if xref_from[1] not in all_field_xref_from:
                all_field_xref_from.append(xref_from[1])
        for field_xref_from_method in all_field_xref_from:
            [c, m, d] = \
                self.inst_analysis_utils.fn_get_class_method_desc_from_method(
                    field_xref_from_method
                )
            field_xref_from_method_string = c + '->' + m + d
            new_chain = chain + ',' + field_xref_from_method_string
            num_locals = self.fn_get_locals(field_xref_from_method)
            instructions = list(field_xref_from_method.get_instructions())
            for index, instruction in enumerate(instructions):
                if (instruction.get_op_value() in 
                        [0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 
                        0x67, 0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D]):
                    operands = instruction.get_operands()
                    last_operand = operands[-1][2]
                    if last_operand != field:
                        continue
                    field_source = operands[0][1]
                    if field_source < num_locals:
                        self.fn_trace_v_reverse(
                            field_xref_from_method,
                            index-1,
                            field_source,
                            chain
                        )
                    else:
                        self.fn_trace_reverse(
                            field_xref_from_method_string,
                            new_chain,
                            field_source - num_locals
                        )
       
    def fn_check_traceto_arg(self, instruction, op_index):
        """Checks if instruction+operand satisfy an ARGTO condition in TRACETO.
        
        Sets a variable to indicate that the condition has been satisfied.
        
        :param instruction: androguard.core.bytecodes.dvm.Instruction
        :param op_index: integer operand index
        """
        if op_index != self.trace_to_argindex:
            return
        operands = instruction.get_operands()
        last_operand = operands[-1][2]
        for item in self.trace_to_list:
            if item in last_operand:
                self.stop_condition = STOP_CONDITION_TRUE
                return

    def fn_check_traceto_result(self, invoked_method_instruction):
        """Checks if an instruction satisfies a RESULTOF condition in TRACETO.
        
        Sets a variable to indicate that the condition has been satisfied.
        
        :param invoked_method_instruction: Androguard EncodedMethod
        """
        operands = invoked_method_instruction.get_operands()
        last_operand = operands[-1][2]
        for item in self.trace_to_list:
            if item in last_operand:
                self.stop_condition = STOP_CONDITION_TRUE
                return
    
    def fn_check_generic_stop_condition(self, check_value):
        """Checks if an instruction satisfies a generic TRACETO condition.
        
        Sets a variable to indicate that the condition has been satisfied.
        
        :param check_value: string to check against trace_to classes/methods
        """
        if self.to_class_method == '<class>':
            check_value = check_value.split('->')[0]
        if check_value in self.trace_to_list:
            self.stop_condition = STOP_CONDITION_TRUE
            return
        
        # Special types of checks for when the traceto is hardcoded.
        if self.hardcoded_traceto == False:
            return
        # This should never be true. Hardcoded traceto's will only have one
        #  value in the list (even with ORs). 
        if len(self.trace_to_list) > 1:
            return
        trace_to_item = self.trace_to_list[0]
        
        # Check for wildcard classes.
        if ((self.to_class_method == '<class>') and ('*' in trace_to_item)):
            trace_to_item = trace_to_item.replace('*', '')
            if trace_to_item in check_value:
                self.stop_condition = STOP_CONDITION_TRUE
            else:
                self.stop_condition = STOP_CONDITION_FALSE
            return
        # Do a partial search for methods only. Do this only when the entire 
        #  trace-to is hardcoded.
        # If traceto is only a class, we can't do much.
        if '->' not in trace_to_item:
            return
        if '->' not in check_value:
            return
        # If traceto doesn't have descriptor, don't proceed.
        # Else, we might end up with way too many FPs.
        if '(' not in trace_to_item:
            return
        if '(' not in check_value:
            return
        if trace_to_item.split('->')[1] == check_value.split('->')[1]:
            self.stop_condition = STOP_CONDITION_MAYBE
            return
    
    def fn_identify_instr_reg(self, calling_method, called_method,
                              reg_position):
        """Identifies the index and register used for a method call.
        
        :param calling_method: Androguard EncodedMethod containing call 
            to method of interest
        :param called_method: string representing method of interest (smali)
        :param reg_position: integer operand index
        :returns: list of (instruction index, register) tuples
        """
        index_reg = []
        instructions = list(calling_method.get_instructions())
        for index, instruction in enumerate(instructions):
            opcode = instruction.get_op_value()
            if (opcode not in 
                    [0x6E, 0x6F, 0x70, 0x71, 0x72,
                     0x74, 0x75, 0x76, 0x77, 0x78]):
                continue
            all_operands = instruction.get_operands()
            method_operand = all_operands[-1][2]
            if called_method in method_operand:
                if reg_position >= (len(all_operands)-1):
                    reg_position = len(all_operands)-2
                operand_of_interest = all_operands[int(reg_position)][1]
                index_reg.append((index, operand_of_interest))
        return index_reg
        
    def fn_identify_result_reg(self, calling_method, called_method):
        """Identifies the index and register of the output of a method call.
        
        :param calling_method: Androguard EncodedMethod containing call 
            to method of interest
        :param called_method: string representing method of interest (smali)
        :returns: list of (instruction index, register) tuples
        """
        index_reg = []
        try:
            instructions = list(calling_method.get_instructions())
        except:
            return []
        for index, instruction in enumerate(instructions):
            opcode = instruction.get_op_value()
            if (opcode not in 
                    [0x6E, 0x6F, 0x70, 0x71, 0x72,
                     0x74, 0x75, 0x76, 0x77, 0x78]):
                continue
            all_operands = instruction.get_operands()
            method_operand = all_operands[-1][2]
            if called_method in method_operand:
                if index == (len(instructions)-1):
                    break
                next_instr = instructions[index+1]
                if next_instr.get_op_value() not in [0x0A, 0x0B, 0x0C]:
                    continue
                result_register = (next_instr.get_operands())[0][1]
                index_reg.append((index+1, result_register))
        return index_reg
    
    def fn_determine_class_method_desc(self, trace_from, trace_from_type=None):
        """Determines the class/method/desc parts based on trace start point.
        
        :param trace_from: string denoting trace start point
        :param trace_from_type: string containing trace start point type 
            (either "<class>" or "<method>")
        :returns: list containing class, method, descriptor parts
        """
        [class_part, method_part, desc_part] = \
            self.inst_analysis_utils.fn_get_class_method_desc_from_string(
                trace_from
            )
        # If we care only about the class part, overwrite the method/desc
        #  parts with '.' (i.e., "don't care")
        if trace_from_type == '<class>':
            method_part = '.'
            desc_part = '.'
        return [class_part, method_part, desc_part]
        
    def fn_get_trace_type(self, string):
        """Gets trace starting point type.
        
        :param string: string containing trace start point type (either 
            "<class>" or "<method>". The string may not directly contain 
            these values, in which case the type will have to be inferred.
        :returns: list containing the start point type and the modified string
            (within the "<class>" or "<method>" indication removed)
        """
        trace_type = '<class>'
        if ':' in string:
            trace_type = string.split(':')[0]                       
            string = string[len(trace_type)+1:]
        else:
            if '->' in string:
                trace_type = '<method>'
        return [trace_type, string]
    
    def fn_get_trace_items(self, string, trace_type):
        """Gets the actual strings to use as start/end points of trace.
        
        :param string: the string specified within the template
        :param trace_type: string (either "<class>" or "<method>"), indicating
            whether the trace should begin/end at the class level or method 
            level
        :returns: list of possible start/end points
        """
        output_items = [] 
        # If the string begins with @, then we need to find linked items.
        if string[0] == '@':
            self.hardcoded_traceto = False
            # If a sub-part has not been specified, then assume that the
            #  entire string is the link name.
            if ']' not in string:
                link_name = string
                link_subpart = ''
                remaining_string = ''
            # If a sub-part has been specified, then split the string to
            #  identify the link name, relevant sub-part, and remainder
            #  of string.
            else:
                split_for_link = string.split(']')
                remaining_string = split_for_link[1]
                second_split = split_for_link[0].split('[')            
                link_name = second_split[0]                
                link_subpart = second_split[1].replace(' ', '')
            # Get all linked items.
            linked_items = self.inst_analysis_utils.fn_get_linked_items(
                self.current_links,
                link_name
            )
            if link_subpart == '':
                for linked_item in linked_items:
                    return_string = linked_item + remaining_string
                    if trace_type == '<class>':
                        return_string = return_string.split('->')[0]
                    output_items.append(return_string)
            elif link_subpart == '<class>':
                for linked_item in linked_items:
                    class_part_only = linked_item.split('->')[0]
                    return_string = class_part_only + remaining_string
                    if trace_type == '<class>':
                        return_string = return_string.split('->')[0]
                    output_items.append(return_string)
            elif link_subpart == '<method>':
                for linked_item in linked_items:
                    if '->' not in linked_item:
                        continue
                    return_string = linked_item + remaining_string
                    if trace_type == '<class>':
                        return_string = return_string.split('->')[0]
                    output_items.append(return_string)
        # If the string doesn't begin with @, then it's a normal string.
        else:
            self.hardcoded_traceto = True
            if trace_type == '<class>':
                string = string.split('->')[0]
            output_items = [string]
        return output_items
    
    def fn_enumerate_trace_source_sinks(self, trace_template):
        """Enumerates the (list of) trace start and end points from template.
        
        :param trace_template: dictionary object corresponding to a single 
            trace, from which trace end points are to be extracted
        :returns: list containing two lists - the first a list of possible 
            start points and the second, a list of possible end points
        """
        # Get the start points.
        trace_from_string = trace_template['TRACEFROM']
        from_arg_index = 0
        trace_from_type = None
        if 'RESULTOF' in trace_from_string:
            trace_from_type = 'RESULTOF'
            trace_from = trace_from_string.split('RESULTOF')[1]
            trace_from = trace_from.strip()
        elif 'ARGTO' in trace_from_string:
            trace_from_type = 'ARGTO'
            trace_from = \
                (trace_from_string.split('ARGTO')[1]).split('ARGINDEX')[0]
            trace_from = trace_from.strip()
            if 'ARGINDEX' in trace_from_string:
                from_arg_index = \
                    int((trace_from_string.split('ARGINDEX')[1]).strip())
        else:
            trace_from = trace_from_string
                
        if ' OR ' in trace_from:
            trace_from_string_list = trace_from.split(' OR ')
        else:
            trace_from_string_list = [trace_from]
            
        # Get the trace ending points.
        trace_to_string = trace_template['TRACETO']
        to_arg_index = None
        trace_to_type = None
        if 'RESULTOF' in trace_to_string:
            trace_to_type = 'RESULTOF'
            trace_to = trace_to_string.split('RESULTOF')[1]
            trace_to = trace_to.strip()
        elif 'ARGTO' in trace_to_string:
            trace_to_type = 'ARGTO'
            trace_to = \
                (trace_to_string.split('ARGTO')[1]).split('ARGINDEX')[0]
            trace_to = trace_to.strip()
            if 'ARGINDEX' in trace_to_string:
                to_arg_index = \
                    int((trace_to_string.split('ARGINDEX')[1]).strip())
        trace_to = trace_to_string

        if ' OR ' in trace_to:
            trace_to_string_list = trace_to.split(' OR ')
        else:
            trace_to_string_list = [trace_to]
        
        # Set variables.
        self.trace_from_main_list = trace_from_string_list
        self.trace_from_type = trace_from_type
        self.trace_from_argindex = from_arg_index
        self.trace_to_main_list = trace_to_string_list
        self.trace_to_type = trace_to_type
        self.trace_to_argindex = to_arg_index

    def fn_analyse_returns(self, trace_template):
        """Analyses the return object and appends items to returns list.
        
        :param trace_template: dictionary object containing RETURN element
        """
        returnables = trace_template['RETURN']
        returnable_elements_name = returnables.split(' AS ')[1]
        return_type = returnables.split(' AS ')[0]

        # Analyse each chain.
        for chain_string in self.output_chains:
            chain = chain_string.split(',')
            if self.trace_direction == TRACE_REVERSE:
                chain.reverse()            
            output_str = ''
            for chain_node in chain:
                chain_node = chain_node.strip()
                if output_str == '':
                    output_str = chain_node
                else:
                    output_str = output_str + ',' + chain_node
            self.current_returns.append({returnable_elements_name: output_str})
            
    def fn_get_jsinterface_classes_methods(self):
        """Gets all classes and methods with JavascriptInterface annotations."""
        jsinterface_methods = set()
        jsinterface_classes = set()
        for method in self.all_annotations:
            if ('Landroid/webkit/JavascriptInterface;' in 
                    self.all_annotations[method]):
                jsinterface_methods.add(method)
                class_part = method.split('->')[0]
                jsinterface_classes.add(class_part)
        self.jsinterface_methods = jsinterface_methods
        self.jsinterface_classes = jsinterface_classes
        
    def fn_get_locals(self, method):
        num_registers = method.code.get_registers_size()
        num_parameter_registers = method.code.get_ins_size()
        num_local_registers = num_registers - num_parameter_registers
        return num_local_registers