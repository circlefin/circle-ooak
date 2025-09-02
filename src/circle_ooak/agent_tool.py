# Copyright (c) 2025 OpenAI
#
# This file is part of OpenAI Agents SDK. The full OpenAI Agents SDK copyright notice, including
# terms governing use, modification, and redistribution, is contained in the
# file LICENSE.MIT at the root of the source code distribution tree.
#
# Portions Copyright (c) 2025, Circle Internet Group, Inc.  All rights reserved
# Circle contributions are licensed under the Apache 2.0 License.
#
# SPDX-License-Identifier: Apache-2.0 AND MIT


# This file creates an agent_tool decorator that can be used to wrap
# both a function and an instance method. It is based on the function_tool decorator
# in OpenAI Agents SDK file tools.py.

import json
import inspect
from pydantic import ValidationError
from agents import (
    RunContextWrapper,
    FunctionTool,
    default_tool_error_function,
    SpanError,
    ModelBehaviorError,
    Agent,
    _debug,
    logger
)
# ToolContext has been replaced by RunContextWrapper in newer versions
from agents.function_schema import DocstringStyle, function_schema
from agents.util._types import MaybeAwaitable
from agents.util import _error_tracing
from agents.logger import logger

from typing import Any, Callable, Union, ParamSpec, Concatenate


# required fields from agents:tools.py
ToolParams = ParamSpec("ToolParams")
ToolFunctionWithoutContext = Callable[ToolParams, Any]
ToolFunctionWithContext = Callable[Concatenate[RunContextWrapper[Any], ToolParams], Any]
ToolFunction = Union[ToolFunctionWithoutContext[ToolParams], ToolFunctionWithContext[ToolParams]]
ToolErrorFunction = Callable[[RunContextWrapper[Any], Exception], MaybeAwaitable[str]]


def agent_tool(
    func: ToolFunction[ToolParams] | None = None,
    *,
    name_override: str | None = None,
    description_override: str | None = None,
    docstring_style: DocstringStyle | None = None,
    use_docstring_info: bool = True,
    failure_error_function: ToolErrorFunction | None = default_tool_error_function,
    strict_mode: bool = True,
    is_enabled: bool | Callable[[RunContextWrapper[Any], Agent[Any]], MaybeAwaitable[bool]] = True,
) -> FunctionTool | Callable[[ToolFunction[ToolParams]], FunctionTool]:
    """
    Decorator to create a FunctionTool from a function. By default, we will:
    1. Parse the function signature to create a JSON schema for the tool's parameters.
    2. Use the function's docstring to populate the tool's description.
    3. Use the function's docstring to populate argument descriptions.
    The docstring style is detected automatically, but you can override it.

    If the function takes a `RunContextWrapper` as the first argument, it *must* match the
    context type of the agent that uses the tool.

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
        strict_mode: Whether to enable strict mode for the tool's JSON schema. We *strongly*
            recommend setting this to True, as it increases the likelihood of correct JSON input.
            If False, it allows non-strict JSON schemas. For example, if a parameter has a default
            value, it will be optional, additional properties are allowed, etc. See here for more:
            https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses#supported-schemas
        is_enabled: Whether the tool is enabled. Can be a bool or a callable that takes the run
            context and agent and returns whether the tool is enabled. Disabled tools are hidden
            from the LLM at runtime.
    """

    def _create_agent_tool(the_func: ToolFunction[ToolParams]) -> FunctionTool:
        # Check if this is a method (first parameter is 'self')
        sig = inspect.signature(the_func)
        params = list(sig.parameters.values())
        is_method = len(params) > 0 and params[0].name == 'self'
        
        if is_method:
            # Create a wrapper function that excludes 'self' from the signature for schema generation
            new_params = params[1:]  # Skip 'self'
            new_sig = sig.replace(parameters=new_params)
            
            # Create a dummy function with the modified signature for schema generation
            def schema_func(*args, **kwargs):
                pass
            schema_func.__signature__ = new_sig
            schema_func.__name__ = the_func.__name__
            schema_func.__doc__ = the_func.__doc__
            
            # Use the wrapper function for schema generation
            schema_function = schema_func
        else:
            schema_function = the_func
        
        schema = function_schema(
            func=schema_function,
            name_override=name_override,
            description_override=description_override,
            docstring_style=docstring_style,
            use_docstring_info=use_docstring_info,
            strict_json_schema=strict_mode,
        )

        # change: add instance argument to the _on_invoke_tool_impl signature
        async def _on_invoke_tool_impl(ctx: RunContextWrapper[Any], input: str, instance: Any = None) -> Any:
            try:
                json_data: dict[str, Any] = json.loads(input) if input else {}
            except Exception as e:
                if _debug.DONT_LOG_TOOL_DATA:
                    logger.debug(f"Invalid JSON input for tool {schema.name}")
                else:
                    logger.debug(f"Invalid JSON input for tool {schema.name}: {input}")
                raise ModelBehaviorError(
                    f"Invalid JSON input for tool {schema.name}: {input}"
                ) from e

            if _debug.DONT_LOG_TOOL_DATA:
                logger.debug(f"Invoking tool {schema.name}")
            else:
                logger.debug(f"Invoking tool {schema.name} with input {input}")

            try:
                parsed = (
                    schema.params_pydantic_model(**json_data)
                    if json_data
                    else schema.params_pydantic_model()
                )
            except ValidationError as e:
                raise ModelBehaviorError(f"Invalid JSON input for tool {schema.name}: {e}") from e
            

            args, kwargs_dict = schema.to_call_args(parsed)

            if not _debug.DONT_LOG_TOOL_DATA:
                logger.debug(f"Tool call args: {args}, kwargs: {kwargs_dict}")

            # change: if instance is not None, call the function with the instance
            if instance is not None:
                if inspect.iscoroutinefunction(the_func):
                    if schema.takes_context:
                        result = await the_func(instance, ctx, *args, **kwargs_dict)
                    else:
                        result = await the_func(instance, *args, **kwargs_dict)
                else:
                    if schema.takes_context:
                        result = the_func(instance, ctx, *args, **kwargs_dict)
                    else:
                        result = the_func(instance, *args, **kwargs_dict)
            else:
                if inspect.iscoroutinefunction(the_func):
                    if schema.takes_context:
                        result = await the_func(ctx, *args, **kwargs_dict)
                    else:
                        result = await the_func(*args, **kwargs_dict)
                else:
                    if schema.takes_context:
                        result = the_func(ctx, *args, **kwargs_dict)
                    else:
                        result = the_func(*args, **kwargs_dict)

            if _debug.DONT_LOG_TOOL_DATA:
                logger.debug(f"Tool {schema.name} completed.")
            else:
                logger.debug(f"Tool {schema.name} returned {result}")

            return result

        async def _on_invoke_tool(ctx: RunContextWrapper[Any], input: str, instance: Any = None) -> Any:
            try:
                return await _on_invoke_tool_impl(ctx, input, instance)
            except Exception as e:
                if failure_error_function is None:
                    raise

                result = failure_error_function(ctx, e)
                if inspect.isawaitable(result):
                    return await result

                _error_tracing.attach_error_to_current_span(
                    SpanError(
                        message="Error running tool (non-fatal)",
                        data={
                            "tool_name": schema.name,
                            "error": str(e),
                        },
                    )
                )
                return result

        return FunctionTool(
            name=schema.name,
            description=schema.description or "",
            params_json_schema=schema.params_json_schema,
            on_invoke_tool=_on_invoke_tool,
            strict_json_schema=strict_mode,
            is_enabled=is_enabled,
        )

    # If func is actually a callable, we were used as @function_tool with no parentheses
    if callable(func):
        return _create_agent_tool(func)

    # Otherwise, we were used as @function_tool(...), so return a decorator
    def decorator(real_func: ToolFunction[ToolParams]) -> FunctionTool:
        return _create_agent_tool(real_func)

    return decorator