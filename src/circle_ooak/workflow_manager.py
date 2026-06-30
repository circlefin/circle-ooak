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

from .secure_tool import SecureContext, SecureContextResponse


class ManagerResponse(SecureContextResponse):
    def __init__(self, approved: bool, msg: str = None):
        super().__init__(approved, msg)




_ALLOWED_INTENT_KEYS = frozenset({"function", "arguments", "instance"})


def _validate_intent_data(intent: dict, label: str) -> ManagerResponse | None:
    unknown = set(intent.keys()) - _ALLOWED_INTENT_KEYS
    if unknown:
        return ManagerResponse(
            False,
            f"{label} intent has unknown keys: {', '.join(sorted(unknown))}",
        )
    if "function" not in intent:
        return ManagerResponse(False, f"{label} intent is missing required key: function")
    if not isinstance(intent["function"], str) or not intent["function"]:
        return ManagerResponse(False, f"{label} intent 'function' must be a non-empty string")
    if "arguments" in intent and not isinstance(intent["arguments"], dict):
        return ManagerResponse(False, f"{label} intent 'arguments' must be an object")
    if "instance" in intent and not isinstance(intent["instance"], str):
        return ManagerResponse(False, f"{label} intent 'instance' must be a string")
    return None


def _validate_intent_string(intent: str, label: str) -> ManagerResponse | None:
    try:
        data = json.loads(intent)
    except json.JSONDecodeError:
        return ManagerResponse(False, f"{label} intent is not valid JSON")
    if not isinstance(data, dict):
        return ManagerResponse(False, f"{label} intent must be a JSON object")
    return _validate_intent_data(data, label)


def _validate_intents(intents: list[str]) -> ManagerResponse | None:
    if not intents:
        return ManagerResponse(False, "Workflow must contain at least one intent")
    for index, intent in enumerate(intents):
        error = _validate_intent_string(intent, f"Intent {index + 1}")
        if error is not None:
            return error
    return None


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
        try:
            current = json.loads(self.intent)
            incoming = json.loads(intent)
        except json.JSONDecodeError:
            approved = self.intent == intent
            msg = "Intents match" if approved else "Intent string mismatch"
            return ManagerResponse(approved, msg)

        for label, data in (("Approved", current), ("Incoming", incoming)):
            error = _validate_intent_data(data, label)
            if error is not None:
                return error

        if current["function"] != incoming["function"]:
            return ManagerResponse(
                False,
                f"Function name mismatch: {current['function']} vs {incoming['function']}",
            )

        if current.get("instance") != incoming.get("instance"):
            return ManagerResponse(
                False,
                f"Instance mismatch: {current.get('instance')} vs {incoming.get('instance')}",
            )

        current_args = current.get("arguments", {})
        incoming_args = incoming.get("arguments", {})
        for key in set(current_args.keys()) | set(incoming_args.keys()):
            if key not in current_args:
                return ManagerResponse(False, f"Missing argument in approved intent: {key}")
            if key not in incoming_args:
                return ManagerResponse(False, f"Missing argument in incoming intent: {key}")
            if current_args[key] != incoming_args[key]:
                return ManagerResponse(
                    False,
                    f"Argument '{key}' mismatch: {current_args[key]} vs {incoming_args[key]}",
                )

        return ManagerResponse(True, "Intents match")

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
            match = current_action.has_matching_intent(intent)
            if not match.approved:
                return ManagerResponse(
                    False,
                    'Cannot start action, current action does not match intent: '
                    + current_action.intent
                    + '. '
                    + match.msg,
                )
            
            # check if current action is not started
            current_action = self.actions[self.current_action]
            if current_action.status != Action.enum['not_started']:
                return ManagerResponse(False, 'Cannot start action, current action is in state: ' +  current_action.status)  
            
            # update status
            current_action.status = Action.enum['in_progress']
            self.log(f"Starting action {current_action.intent}")
            return ManagerResponse(True, 'Action started successfully')

    def complete(self, intent: str, result: any) -> ManagerResponse:
        with self._lock:
            # Records handler outcome. Authorization already happened in start().
            if self.current_action >= len(self.actions):
                self.log("complete called with no pending action")
                return ManagerResponse(True, "No action to complete")

            current_action = self.actions[self.current_action]
            if current_action.status == Action.enum['in_progress']:
                current_action.result = result
                current_action.status = Action.enum['completed']
                self.current_action += 1

                if self.current_action >= len(self.actions):
                    self.status = Workflow.enum['completed']
                    self.result = result
                    self.log(f"Finished action {current_action.intent} with result {result}")
                    self.log(f"Workflow completed successfully with result {result}")
                    return ManagerResponse(True, "Workflow completed successfully")

                next_action = self.actions[self.current_action]
                next_action.status = Action.enum['not_started']
                self.log(f"Finished action {current_action.intent} with result {result}")
                return ManagerResponse(True, "Action completed successfully, ready for next action")

            self.log(
                "complete called for action not in progress: "
                + current_action.intent
                + " with status: "
                + current_action.status
            )
            return ManagerResponse(True, "Action already finalized")

    def fail(self, intent: str, error: str) -> ManagerResponse:
        with self._lock:
            # Best-effort failure recording. Must not raise or reject after handler errors.
            if self.current_action < len(self.actions):
                current_action = self.actions[self.current_action]
                if current_action.status == Action.enum['in_progress']:
                    current_action.result = error
                    current_action.status = Action.enum['failed']
                    self.status = Workflow.enum['failed']
                    self.result = error
                    self.log(f"Failed action {current_action.intent} with error {error}")
                else:
                    self.log(
                        "fail called for action not in progress: "
                        + current_action.intent
                        + " with status: "
                        + current_action.status
                    )
            else:
                self.log("fail called with no pending action")
            return ManagerResponse(True, "Action failed")

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
        self.log(f"Approved workflow {workflow.wfid} with intents: {workflow.actions}.\nOverride this method with your own approval logic.")
        return ManagerResponse(True, 'Approved')

    # AI agents can call this function to get approval for a workflow
    def approve(self, intents: list[str]) -> ManagerResponse:
        self.log(f"Approving workflow with intents: {intents}")
        validation = _validate_intents(intents)
        if validation is not None:
            return validation

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

    def fail(self, wfid: str, intent: str, error: str) -> ManagerResponse:
        if wfid not in self.workflows:
            return ManagerResponse(False, 'Workflow not found')

        workflow = self.workflows[wfid]
        return workflow.fail(intent, error)

    # Implementation of SecureContext interface
    def before_invoke_tool(self, wfid: str, intent: str) -> ManagerResponse:
        return self.start(wfid, intent)
    
    def after_invoke_tool(self, wfid: str, intent: str, result: str) -> ManagerResponse:
        return self.complete(wfid, intent, result)

    def on_invoke_tool_failure(self, wfid: str, intent: str, error: str) -> ManagerResponse:
        return self.fail(wfid, intent, error)







