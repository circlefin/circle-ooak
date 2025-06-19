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
    Agent,
    RunContextWrapper,
    FunctionTool,
    OpenAIChatCompletionsModel,
)
import copy
from typing import Any

class InstanceAgent(Agent):
    def __init__(self, name: str, instructions: str, model: OpenAIChatCompletionsModel, tools: list[FunctionTool] = None, agent_tools: list[FunctionTool] = None):
        # Handle None or empty cases
        if tools is None:
            tools = []
        if agent_tools is None:
            agent_tools = []

        bound_agent_tools = []
        for agent_tool in agent_tools:
            bound_tool = self.attach_instance_to_agent_tool(agent_tool)
            bound_agent_tools.append(bound_tool)

        super().__init__(name=name, instructions=instructions, model=model, tools=tools + bound_agent_tools)

    def attach_instance_to_agent_tool(self, agent_tool: FunctionTool) -> FunctionTool:
        return InstanceAgent.attach_instance(agent_tool, instance=self)
    
    @classmethod
    def attach_instance(cls, agent_tool: FunctionTool, instance: Any) -> FunctionTool:
        # Create a proper deep copy of the FunctionTool to avoid shared state
        new_tool = FunctionTool(
            name=agent_tool.name,
            description=agent_tool.description,
            params_json_schema=copy.deepcopy(agent_tool.params_json_schema),
            on_invoke_tool=None,  # We'll set this below
            strict_json_schema=getattr(agent_tool, 'strict_json_schema', True),
            is_enabled=agent_tool.is_enabled,
        )
        
        # Get the original on_invoke function
        original_on_invoke = agent_tool.on_invoke_tool

        async def new_on_invoke_tool(ctx: RunContextWrapper[Any], input: str, passed_instance: Any = None) -> str:
            # Use the bound instance, not any provided instance
            return await original_on_invoke(ctx, input, instance)

        new_tool.on_invoke_tool = new_on_invoke_tool
        return new_tool