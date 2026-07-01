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
import inspect
import copy
from abc import ABC, abstractmethod
from agents import (
    Agent,
    RunContextWrapper,
    FunctionTool,
    default_tool_error_function,
    SpanError
)
from agents.function_schema import DocstringStyle
from agents.util._types import MaybeAwaitable
from agents.util._error_tracing import attach_error_to_current_span

from typing import Any, Callable, Union, ParamSpec, Concatenate

from .agent_tool import agent_tool


def get_instance_id(instance: Any) -> str:
    if isinstance(instance, Agent) or hasattr(instance, "name"):
        name = instance.name
        if getattr(instance, "bind_to_instance", False):
            return f"{name}_{id(instance)}"
        return name
    if hasattr(instance, "__str__"):
        return str(instance)
    return f"{instance.__class__.__name__}_{hex(id(instance))}"


def strip_wfid_from_args(json_data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in json_data.items() if k != "wfid"}


def inject_wfid_into_schema(tool: FunctionTool) -> None:
    schema = copy.deepcopy(tool.params_json_schema)
    properties = schema.setdefault("properties", {})
    properties["wfid"] = {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "description": "Workflow id from approval, or null to receive the intent JSON.",
    }
    required = list(schema.get("required", []))
    if "wfid" not in required:
        required.append("wfid")
    schema["required"] = required
    tool.params_json_schema = schema


class SecureContextResponse: 
    def __init__(self, approved: bool, msg: str = None):
        self.approved = approved
        self.msg = msg

class SecureContext(ABC):
    def __init__(self, managed_context: dict[str, any] = None):
        self.managed_context = managed_context or {}

    @abstractmethod
    def before_invoke_tool(self, wfid: str, intent: str) -> SecureContextResponse:
        pass

    @abstractmethod
    def after_invoke_tool(self, wfid: str, intent: str, result: str) -> SecureContextResponse:
        pass

    def on_invoke_tool_failure(self, wfid: str, intent: str, error: str) -> SecureContextResponse:
        """Called when a secure tool raises after before_invoke_tool succeeded."""
        return SecureContextResponse(True, "Ignored")

# required fields from agents:tools.py
ToolParams = ParamSpec("ToolParams")
ToolFunctionWithoutContext = Callable[ToolParams, Any]
ToolFunctionWithContext = Callable[Concatenate[RunContextWrapper[Any], ToolParams], Any]
ToolFunction = Union[ToolFunctionWithoutContext[ToolParams], ToolFunctionWithContext[ToolParams]]
ToolErrorFunction = Callable[[RunContextWrapper[Any], Exception], MaybeAwaitable[str]]


def secure_tool(
    func: ToolFunction[ToolParams] | None = None,
    *,
    name_override: str | None = None,
    description_override: str | None = None,
    docstring_style: DocstringStyle | None = None,
    use_docstring_info: bool = True,
    failure_error_function: ToolErrorFunction | None = default_tool_error_function,
) -> FunctionTool | Callable[[ToolFunction[ToolParams]], FunctionTool]:
    """
    A secure version of the function_tool decorator that adds additional security checks and hooks.
    It inherits all functionality from function_tool and adds:
    1. Intent checking - verifies if the intent argument is present and calls intent()
    2. Pre/post execution hooks - calls do_before() and do_after() around function execution

    Args:
        func: The function to wrap.
        name_override: If provided, use this name for the tool instead of the function's name.
        description_override: If provided, use this description for the tool instead of the
            function's docstring.
        docstring_style: If provided, use this style for the tool's docstring. If not provided,
            we will attempt to auto-detect the style.
        use_docstring_info: If True, use the function's docstring to populate the tool's
            description and argument descriptions.
        failure_error_function: If provided, use this function to generate an error message when
            the tool call fails. The error message is sent to the LLM. If you pass None, then no
            error message will be sent and instead an Exception will be raised.
    """

    def _create_secure_function_tool(the_func: ToolFunction[ToolParams]) -> FunctionTool:
        # First create the base function tool
        system_prompt = f"""
        This is a secure tool. You must include a 'wfid' field in your function call arguments.
        If you call the tool with "wfid": None, it will return the intent that needs to be executed.
        You can use this intent to get approval from the user.
        """
        
        base_tool = agent_tool(
            func=the_func,
            name_override=name_override,
            description_override=description_override,
            docstring_style=docstring_style,
            use_docstring_info=use_docstring_info,
            failure_error_function=None,
        )
        inject_wfid_into_schema(base_tool)

        # Append system_prompt to the tool's description
        if hasattr(base_tool, 'description') and base_tool.description:
            base_tool.description = base_tool.description + "\n\n" + system_prompt
        elif hasattr(base_tool, 'description'):
            base_tool.description = system_prompt

        # Create a new on_invoke_tool that wraps the original with security checks
        original_on_invoke = base_tool.on_invoke_tool

        def make_intent(json_data: dict[str, Any], instance: Any = None) -> str:
            args_without_wfid = strip_wfid_from_args(json_data)
            formatted_data = {
                "function": base_tool.name,
                "arguments": args_without_wfid
            }
            if instance is not None:
                formatted_data["instance"] = get_instance_id(instance)
            return json.dumps(formatted_data)

        async def before_invoke_tool(ctx: RunContextWrapper[Any], wfid: str, intent: str) -> dict[str, Any]:
            security_hooks: SecureContext = ctx.context
            return security_hooks.before_invoke_tool(wfid, intent)
        
        async def after_invoke_tool(ctx: RunContextWrapper[Any], wfid: str, intent: str, result: str) -> str:
            security_hooks: SecureContext = ctx.context
            return security_hooks.after_invoke_tool(wfid, intent, result)

        async def fail_invoke_tool(ctx: RunContextWrapper[Any], wfid: str, intent: str, error: str) -> SecureContextResponse:
            security_hooks: SecureContext = ctx.context
            return security_hooks.on_invoke_tool_failure(wfid, intent, error)

        async def secure_on_invoke_tool(ctx: RunContextWrapper[Any], input: str, instance: Any = None) -> str:
            try:
                # get intent from input
                json_data: dict[str, Any] = json.loads(input) if input else {}
                intent = make_intent(json_data, instance)

                # Extract wfid from the input JSON
                wfid_value = json_data.get('wfid')
                if wfid_value is not None and wfid_value != "":
                    wfid = wfid_value
                else:
                    # no wfid: caller just wants to get the intent
                    return intent

                # Call security hooks before_invoke_tool
                status = await before_invoke_tool(ctx, wfid, intent)
                if not status.approved:
                    return status.msg

                handler_input = json.dumps(strip_wfid_from_args(json_data))
                try:
                    if instance is not None:
                        result = await original_on_invoke(ctx, handler_input, instance)
                    else:
                        result = await original_on_invoke(ctx, handler_input)
                except Exception as e:
                    await fail_invoke_tool(ctx, wfid, intent, str(e))
                    if failure_error_function is None:
                        raise
                    result = failure_error_function(ctx, e)
                    if inspect.isawaitable(result):
                        result = await result
                    attach_error_to_current_span(
                        SpanError(
                            message="Error running secure tool (non-fatal)",
                            data={
                                "tool_name": base_tool.name,
                                "error": str(e),
                            },
                        )
                    )
                    return result

                status = await after_invoke_tool(ctx, wfid, intent, result)
                if not status.approved:
                    return status.msg

                return result

            except Exception as e:
                if failure_error_function is None:
                    raise

                result = failure_error_function(ctx, e)
                if inspect.isawaitable(result):
                    result = await result

                attach_error_to_current_span(
                    SpanError(
                        message="Error running secure tool (non-fatal)",
                        data={
                            "tool_name": base_tool.name,
                            "error": str(e),
                        },
                    )
                )
                return result

        # now override the on_invoke_tool with the secure version
        base_tool.on_invoke_tool = secure_on_invoke_tool

        return base_tool

    # If func is actually a callable, we were used as @secure_tool with no parentheses
    if callable(func):
        return _create_secure_function_tool(func)

    # Otherwise, we were used as @secure_tool(...), so return a decorator
    def decorator(real_func: ToolFunction[ToolParams]) -> FunctionTool:
        return _create_secure_function_tool(real_func)

    return decorator
