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

from agents import (
    function_tool,
    RunContextWrapper,
    OpenAIChatCompletionsModel
)
from typing import Any
from instance_agent import InstanceAgent
from secure_tool import secure_tool, agent_tool
from workflow_manager import WorkflowManager


class Wallet:
    def __init__(self, address: str):
        self.address = address
    
    def send_usdc(self, receiver: str, amount: int):
        print(f"Sending {amount} USDC from {self.address} to {receiver}")
        return "txhash=1234567890"
    
    def mint_usdc(self, receiver: str, amount: int):
        print(f"Minting {amount} USDC by {self.address} to {receiver}")
        return "txhash=0987654321"


# define a mock wallet
class WalletInstanceAgent(InstanceAgent):
    def __init__(self, name: str, model: OpenAIChatCompletionsModel, wallets: dict[str, Wallet]):
        self.wallets = wallets
        instructions = "A wallet agent that can send and mint USDC"
        agent_tools = [self.send_usdc, self.mint_usdc]
        super().__init__(name=name, instructions=instructions, model=model, tools=None, agent_tools=agent_tools)

    @agent_tool
    def send_usdc(self, sender: str, receiver: str, amount: int):
        wallet = self.wallets[sender]
        if wallet is None:
            return f"Wallet {sender} not found"
        return wallet.send_usdc(receiver, amount)

    @agent_tool
    def mint_usdc(self, minter: str, receiver: str, amount: int):
        wallet = self.wallets[minter]
        if wallet is None:
            return f"Wallet {minter} not found"
        return wallet.mint_usdc(receiver, amount)

# define a mock wallet
class WalletWorkflowAgent(InstanceAgent):
    instructions = """
    You help users execute Ethereum transactions. Do the following steps to help the user:
    1. Create a workflow of intents by calling each secure tool with wfid=None to get the intents
    2. Call approve_workflow with the list of intents to get a workflow id 
    3. Execute the workflow by calling each secure tool again. You MUST include the wfid parameter with the workflow id you got in step 2.
    4. Print the final tx hash for every transaction.
    
    You do not need approval from the user to execute a workflow if you have the workflow id.
    """
    def __init__(self, name: str, model: OpenAIChatCompletionsModel, wallets: dict[str, Wallet]):
        self.wallets = wallets
        tools = [self.approve_workflow]
        agent_tools = [self.send_usdc, self.mint_usdc]
        super().__init__(name=name, instructions=self.instructions, model=model, tools=tools, agent_tools=agent_tools)

    @secure_tool
    # all secure tools must have arguments RunContextWrapper[WorkflowManager] and wfid: str
    def send_usdc(self, ctxt: RunContextWrapper[WorkflowManager], wfid: str, sender: str, receiver: str, amount: int):
        wallet = self.wallets[sender]
        if wallet is None:
            return f"Wallet {sender} not found"
        return wallet.send_usdc(receiver, amount)

    @secure_tool
    # all secure tools must have arguments RunContextWrapper[WorkflowManager] and wfid: str
    def mint_usdc(self, ctxt: RunContextWrapper[WorkflowManager], wfid: str, minter: str, receiver: str, amount: int):
        wallet = self.wallets[minter]
        if wallet is None:
            return f"Wallet {minter} not found"
        return wallet.mint_usdc(receiver, amount)

    # define a regular function tool that will be used to approve a workflow
    @function_tool
    def approve_workflow(ctxt: RunContextWrapper[WorkflowManager], workflow: list[str]):
        """Approve a workflow of secure tool calls.
        workflow: a list of intents (json strings). You can get the intents by calling the secure tools with wfid=None.
        returns: a string with the workflow id
        """
        manager = ctxt.context
        response = manager.approve(workflow)
        if response.approved:
            return f"Workflow approved: with wfid {response.msg}"
        else:
            return f"Workflow not approved: {response.msg}"


