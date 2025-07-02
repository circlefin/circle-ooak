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
from circle_ooak.workflow_manager import WorkflowManager
from circle_ooak.instance_agent import InstanceAgent
from circle_ooak.secure_tool import secure_tool
from circle_ooak.agent_tool import agent_tool

# define two static functions that are secure tools that we want to test
@secure_tool
def send_usdc(wfid: str, sender: str, receiver: str, amount: int):
    print(f"Sending {amount} USDC from {sender} to {receiver}")
    return "txhash=1234567890"

@secure_tool
def mint_usdc(wfid: str, minter: str, receiver: str, amount: int):
    print(f"Minting {amount} USDC by {minter} to {receiver}")
    return "txhash=1234567890"

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
    def mint_usdc(self, wfid: str, receiver: str, amount: int):
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


if __name__ == "__main__":
    unittest.main()