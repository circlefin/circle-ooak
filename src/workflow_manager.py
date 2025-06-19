# Copyright 2025 Circle Internet Group, Inc. All rights reserved.
#
#  SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import uuid
import threading

from secure_tool import SecureContext, SecureContextResponse


class ManagerResponse(SecureContextResponse):
    def __init__(self, approved: bool, msg: str = None):
        super().__init__(approved, msg)

class Action:
    enum = {
        'not_started': 'not_started',
        'in_progress': 'in_progress',
        'completed': 'completed',
        'failed': 'failed'
    }

    def __init__(self, intent: str):
        self.intent = intent
        self.status = Action.enum['not_started']
        self.result = None
    
    def __str__(self):
        return self.intent
    
    def __repr__(self):
        return self.intent

    def has_matching_intent(self, intent: str) -> ManagerResponse:
        # Compare JSON contents instead of string format to handle spacing differences
        try:
            current = json.loads(self.intent)
            incoming = json.loads(intent)
            
            # Compare function names
            if current.get('function_name') != incoming.get('function_name') and current.get('function') != incoming.get('function'):
                if self.intent != intent:
                    return ManagerResponse(False, f"Function name mismatch: {current.get('function_name', current.get('function'))} vs {incoming.get('function_name', incoming.get('function'))}")
            
            # Compare arguments
            current_args = {k: v for k, v in current.get('args', current.get('arguments', {})).items()}
            incoming_args = {k: v for k, v in incoming.get('args', incoming.get('arguments', {})).items()}
            
            # Check if arguments match
            if current_args != incoming_args:
                if self.intent != intent:
                    # Debugging output for mismatches
                    for key in set(current_args.keys()) | set(incoming_args.keys()):
                        if key not in current_args:
                            return ManagerResponse(False, f"Missing argument in current intent: {key}")
                        elif key not in incoming_args:
                            return ManagerResponse(False, f"Missing argument in incoming intent: {key}")
                        elif current_args[key] != incoming_args[key]:
                            return ManagerResponse(False, f"Argument '{key}' mismatch: {current_args[key]} vs {incoming_args[key]}")
            
            # If we get here, the intents match
            return ManagerResponse(True, 'Intents match')
            
        except json.JSONDecodeError:
             # Fall back to string comparison if JSON parsing fails
            return ManagerResponse(self.intent == intent, 'Intents match')

class Workflow:
    enum = {
        'not_approved': 'not_approved',
        'approved': 'approved',
        'rejected': 'rejected',
        'completed': 'completed',
        'failed': 'failed'
    }

    def __init__(self, intents: list[str], verbose: bool = False):
        self.actions = [Action(intent) for intent in intents]
        self.verbose = verbose
        self.current_action = 0
        self.status = Workflow.enum['not_approved']
        self.wfid = str(uuid.uuid4())
        self.result = None
        self._lock = threading.Lock()  # Add lock for thread safety

    def log(self, message: str):
        if self.verbose:
            print("LOG: " + message)

    # todo: make thread safe
    def start(self, intent: str) -> ManagerResponse:
        with self._lock:  # Use lock to ensure thread safety
            # check if workflow is approved
            if self.status != Workflow.enum['approved']:
                return ManagerResponse(False, 'Cannot start action, workflow status is: ' + self.status)
             
            # check if we've completed all actions
            if self.current_action >= len(self.actions):
                return ManagerResponse(False, 'All actions have been completed')
            
            # check if current action matches intent
            current_action = self.actions[self.current_action]
            if not current_action.has_matching_intent(intent):
                return ManagerResponse(False, 'Cannot start action, current action does not match intent: ' + current_action.intent + ' with status: ' + current_action.status)
            
            # check if current action is not started
            current_action = self.actions[self.current_action]
            if current_action.status != Action.enum['not_started']:
                return ManagerResponse(False, 'Cannot start action, current action is in state: ' +  current_action.status)  
            
            # update status
            current_action.status = Action.enum['in_progress']
            self.log(f"Starting action {current_action.intent}")
            return ManagerResponse(True, 'Action started successfully')

    def complete(self, intent: str, result: any) -> ManagerResponse:
        with self._lock:  # Use lock to ensure thread safety
            # check if we've completed all actions
            if self.current_action >= len(self.actions):
                return ManagerResponse(False, 'All actions have been completed')
                
            # check if current action matches intent
            current_action = self.actions[self.current_action]
            if not current_action.has_matching_intent(intent):
                return ManagerResponse(False, 'Cannot complete action, current action does not match intent: ' + current_action.intent + ' with status: ' + current_action.status)
            
            # check if action is in progress
            if current_action.status != Action.enum['in_progress']:
                return ManagerResponse(False, 'Cannot complete action, current action is not in progress: ' + current_action.intent + ' with status: ' + current_action.status)
            
            # update result and status
            current_action.result = result
            current_action.status = Action.enum['completed']
            
            # Move to next action
            self.current_action += 1
            
            # If we've completed all actions, update workflow status
            if self.current_action >= len(self.actions):
                self.status = Workflow.enum['completed']
                self.result = result
                self.log(f"Finished action {current_action.intent} with result {result}")
                self.log(f"Workflow completed successfully with result {result}")
                return ManagerResponse(True, 'Workflow completed successfully')
            else:
                # Reset the next action's status to not_started if it exists
                next_action = self.actions[self.current_action]
                next_action.status = Action.enum['not_started']
                self.log(f"Finished action {current_action.intent} with result {result}")
                return ManagerResponse(True, 'Action completed successfully, ready for next action')

class WorkflowManager(SecureContext):
    def __init__(self, verbose: bool = False, managed_context: dict[str, any] = None):
        super().__init__(managed_context)
        self.workflows = {}  # Store workflow states and results
        self.verbose = verbose

    def log(self, message: str):
        if self.verbose:
            print("LOG: " + message)

    # override this method to get approval from UI
    def get_approval(self, workflow: Workflow) -> ManagerResponse:
        self.log(f"Approving workflow {workflow.wfid} with intents: {workflow.actions}.\nOverride this method with your own approval logic.")
        return ManagerResponse(True, 'Approved')

    # AI agents can call this function to get approval for a workflow
    def approve(self, intents: list[str]) -> ManagerResponse:
        self.log(f"Approving workflow with intents: {intents}")
        # generate workflow and wfid
        workflow = Workflow(intents, self.verbose)
        wfid = workflow.wfid

        # get user approval from UI
        user_approval = self.get_approval(workflow)
        if not user_approval.approved:
            return user_approval

        # save approval
        self.workflows[wfid] = workflow
        workflow.status = Workflow.enum['approved']
        return ManagerResponse(True, wfid)
    
    # before_invoke_tool calls this function to start the workflow
    def start(self, wfid: str, intent: str) -> ManagerResponse:
        if wfid not in self.workflows:
            return ManagerResponse(False, 'Workflow not found')
        
        workflow = self.workflows[wfid]
        return workflow.start(intent)
    
    # after_invoke_tool calls this function to complete the workflow
    def complete(self, wfid: str, intent: str, result: any) -> ManagerResponse:
        if wfid not in self.workflows:
            return ManagerResponse(False, 'Workflow not found')
        
        workflow = self.workflows[wfid]
        return workflow.complete(intent, result)

    # Implementation of SecureContext interface
    def before_invoke_tool(self, wfid: str, intent: str) -> ManagerResponse:
        return self.start(wfid, intent)
    
    def after_invoke_tool(self, wfid: str, intent: str, result: str) -> ManagerResponse:
        return self.complete(wfid, intent, result)







