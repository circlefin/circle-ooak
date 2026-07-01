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
import unittest

from agents import RunContextWrapper
from circle_ooak.workflow_manager import WorkflowManager, Action, Workflow
from circle_ooak.instance_agent import InstanceAgent
from circle_ooak.secure_tool import secure_tool, agent_tool, get_instance_id

# define two static functions that are secure tools that we want to test
@secure_tool
def send_usdc(sender: str, receiver: str, amount: int):
    print(f"Sending {amount} USDC from {sender} to {receiver}")
    return "txhash=1234567890"

@secure_tool
def mint_usdc(minter: str, receiver: str, amount: int):
    print(f"Minting {amount} USDC by {minter} to {receiver}")
    return "txhash=1234567890"

@secure_tool
def failing_mint(minter: str, receiver: str, amount: int):
    raise RuntimeError("mint failed")

# define a class that has a method that is an agent tool
class Wallet:
    def __init__(self, address: str):
        self.address = address
    
    @agent_tool
    def mint_usdc(self, wfid: str, receiver: str, amount: int):
        print(f"Sending {amount} USDC from {self.address} to {receiver}")
        return "txhash=1234567890"
    
    @agent_tool
    def get_address(self):
        return self.address
    
# define a class that has a method that is a secure agent tool
class PermissionedWallet:
    def __init__(self, address: str):
        self.address = address
    
    @secure_tool
    def mint_usdc(self, receiver: str, amount: int):
        print(f"Sending {amount} USDC from {self.address} to {receiver}")
        return "txhash=1234567890"


class TestWorkflowAndTools(unittest.IsolatedAsyncioTestCase):
    """Test suite for workflow management and tool execution."""

    async def test_workflow(self):
        """Test creating and executing a workflow with secure tools."""
        # create a RunContextWrapper that will be used to invoke the tools directly
        manager = WorkflowManager(verbose=True)
        context = RunContextWrapper(manager)

        # create a workflow of two intents
        print("Creating workflow of two intents: mint USDC and send USDC")
        tool = mint_usdc
        input_data_1 = {"wfid": None, "minter": "0x1234567890", "receiver": "0x9876543210", "amount": 100}
        intent1 = await tool.on_invoke_tool(context, json.dumps(input_data_1))

        tool = send_usdc
        input_data_2 = {"wfid": None, "sender": "0x9876543210", "receiver": "0xaabbccdd", "amount": 25}
        intent2 = await tool.on_invoke_tool(context, json.dumps(input_data_2))
        workflow = [
            intent1,
            intent2
        ]
        wfid = manager.approve(workflow).msg
        print()

        # start the workflow
        print("Starting workflow")
        tool = mint_usdc
        input_data_1 = {"wfid": wfid, "minter": "0x1234567890", "receiver": "0x9876543210", "amount": 100}
        output = await tool.on_invoke_tool(context, json.dumps(input_data_1))
        print(f"My result: {output}")
        self.assertIsNotNone(output)
        print()

        tool = send_usdc
        input_data_2 = {"wfid": wfid, "sender": "0x9876543210", "receiver": "0xaabbccdd", "amount": 25}
        output = await tool.on_invoke_tool(context, json.dumps(input_data_2))
        print(f"My result: {output}")
        self.assertIsNotNone(output)
        print()

    async def test_agent_tool(self):
        """Test creating and executing an agent tool."""
        print("Starting workflow")
        wallet = Wallet("0x9876543210")
        # attach the instance to the method tool (if this was an agent it would do this automatically in constructor)
        tool = InstanceAgent.attach_instance(wallet.mint_usdc, wallet)
        wfid = "WFID-1234567890"
        input_data_1 = {"wfid": wfid, "receiver": "0x111111", "amount": 100}
        context = RunContextWrapper(None)
        output = await tool.on_invoke_tool(context, json.dumps(input_data_1))
        print(f"My result: {output}")
        self.assertIsNotNone(output)
        print()

    async def test_secure_agent_tool(self):
        """Test creating and executing a secure agent tool."""
        manager = WorkflowManager(verbose=True)
        context = RunContextWrapper(manager)

        # create a workflow of one intent
        print("Creating workflow of one intent: mint USDC")
        wallet = PermissionedWallet("0x9876543210")
        # attach the instance to the method tool (similar to how agent_tool works)
        tool = InstanceAgent.attach_instance(wallet.mint_usdc, wallet)
        input_data_1 = {"wfid": None, "receiver": "0x111111", "amount": 100}
        intent1 = await tool.on_invoke_tool(context, json.dumps(input_data_1))
        workflow = [
            intent1,
        ]
        wfid = manager.approve(workflow).msg
        print()

        # start the workflow
        print("Starting workflow")
        tool = InstanceAgent.attach_instance(wallet.mint_usdc, wallet)
        input_data_1 = {"wfid": wfid, "receiver": "0x111111", "amount": 100}
        output = await tool.on_invoke_tool(context, json.dumps(input_data_1))
        print(f"My result: {output}")
        self.assertIsNotNone(output)
        print()


    async def test_instance_agent_tool(self):
        """Test that the instance is properly attached to the tool"""
        input_data = {}
        context = RunContextWrapper(None)

        wallet_a = Wallet("0xaa")
        tool_a = InstanceAgent.attach_instance(wallet_a.get_address, wallet_a)
        address_a = await tool_a.on_invoke_tool(context, json.dumps(input_data))
        self.assertEqual(address_a, wallet_a.address)

        wallet_b = Wallet("0xbb")
        tool_b = InstanceAgent.attach_instance(wallet_b.get_address, wallet_b)
        address_b = await tool_b.on_invoke_tool(context, json.dumps(input_data))
        self.assertEqual(address_b, wallet_b.address)

        #make sure tool_a is still attached to wallet_a
        address_a = await tool_a.on_invoke_tool(context, json.dumps(input_data))
        self.assertEqual(address_a, wallet_a.address) # this should succeed

    def test_get_instance_id_bind_to_instance(self):
        class NamedStub:
            def __init__(self, name: str, bind_to_instance: bool = False):
                self.name = name
                self.bind_to_instance = bind_to_instance

        by_name = NamedStub("Secure Agent", bind_to_instance=False)
        self.assertEqual(get_instance_id(by_name), "Secure Agent")

        by_object = NamedStub("Secure Agent", bind_to_instance=True)
        self.assertEqual(get_instance_id(by_object), f"Secure Agent_{id(by_object)}")


class TestWorkflowSecurity(unittest.IsolatedAsyncioTestCase):
    """Regression tests for workflow intent enforcement."""

    def test_rejects_altered_arguments_after_approval(self):
        approved = json.dumps(
            {
                "function": "send_usdc",
                "arguments": {"sender": "0xA", "receiver": "0xB", "amount": 1},
                "instance": "Secure Agent",
            }
        )
        altered = json.dumps(
            {
                "function": "send_usdc",
                "arguments": {"sender": "0xA", "receiver": "0xC", "amount": 999},
                "instance": "Secure Agent",
            }
        )

        action = Action(approved)
        match = action.has_matching_intent(altered)
        self.assertFalse(match.approved)
        self.assertIn("mismatch", match.msg)

        manager = WorkflowManager()
        wfid = manager.approve([approved]).msg
        start = manager.start(wfid, altered)
        self.assertFalse(start.approved)

    def test_rejects_different_tool_with_same_arguments(self):
        approved = json.dumps(
            {
                "function": "approved_transfer",
                "arguments": {"receiver": "0xB", "amount": 1},
            }
        )
        dangerous = json.dumps(
            {
                "function": "dangerous_transfer",
                "arguments": {"receiver": "0xB", "amount": 1},
            }
        )

        action = Action(approved)
        match = action.has_matching_intent(dangerous)
        self.assertFalse(match.approved)
        self.assertIn("Function name mismatch", match.msg)

        manager = WorkflowManager()
        wfid = manager.approve([approved]).msg
        start = manager.start(wfid, dangerous)
        self.assertFalse(start.approved)

    def test_approve_rejects_invalid_intent_shape(self):
        manager = WorkflowManager()

        empty = manager.approve([])
        self.assertFalse(empty.approved)
        self.assertIn("at least one intent", empty.msg)

        bad_json = manager.approve(["not json"])
        self.assertFalse(bad_json.approved)
        self.assertIn("not valid JSON", bad_json.msg)

        missing_function = manager.approve([json.dumps({"arguments": {}})])
        self.assertFalse(missing_function.approved)
        self.assertIn("function", missing_function.msg)

        unknown_key = manager.approve(
            [json.dumps({"function": "send_usdc", "arguments": {}, "wfid": "x"})]
        )
        self.assertFalse(unknown_key.approved)
        self.assertIn("unknown keys", unknown_key.msg)

    async def test_tool_exception_marks_action_failed(self):
        manager = WorkflowManager(verbose=True)
        context = RunContextWrapper(manager)

        input_data = {"wfid": None, "minter": "0x1", "receiver": "0x2", "amount": 1}
        intent = await failing_mint.on_invoke_tool(context, json.dumps(input_data))
        wfid = manager.approve([intent]).msg
        workflow = manager.workflows[wfid]

        execute_data = {"wfid": wfid, "minter": "0x1", "receiver": "0x2", "amount": 1}
        output = await failing_mint.on_invoke_tool(context, json.dumps(execute_data))
        self.assertIsNotNone(output)

        action = workflow.actions[0]
        self.assertEqual(action.status, Action.enum["failed"])
        self.assertEqual(action.result, "mint failed")
        self.assertEqual(workflow.status, Workflow.enum["failed"])

        retry = manager.start(wfid, intent)
        self.assertFalse(retry.approved)
        self.assertIn("failed", retry.msg)


if __name__ == "__main__":
    unittest.main()