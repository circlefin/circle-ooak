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

import asyncio
import dotenv
import os
import sys

from openai import AsyncOpenAI


from agents import (
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
)
from workflow_manager import WorkflowManager
from example.wallet_agent import WalletInstanceAgent, WalletWorkflowAgent, Wallet

# load AI model from environment variables
# these can be set in an .env file or in the environment
dotenv.load_dotenv()
BASE_URL = os.getenv("OPENAI_URL") or ""
API_KEY = os.getenv("OPENAI_API_KEY") or ""
MODEL_NAME = os.getenv("OPENAI_MODEL") or ""
if not BASE_URL or not API_KEY or not MODEL_NAME:
    print(f'BASE_URL: {BASE_URL}, API_KEY: {API_KEY}, MODEL_NAME: {MODEL_NAME}')
    raise ValueError(
        "Please set OPENAI_URL, OPENAI_API_KEY, MODEL_NAME via env var or .env file"
    )
client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)
set_tracing_disabled(disabled=True)
model = OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=client)


async def ask_and_respond(agent, question, manager, chat_history=None):
    if chat_history is None:
        chat_history = []
        question = [{"role": "user", "content": question}]
    else:
        # todo: limit chat history to 10 messages
        question = chat_history + [{"role": "user", "content": question}]

    result = await Runner.run(agent, question, context=manager)
    print(result.final_output)
    return result.to_input_list()

async def run_wallet_workflow_agent():
    print("I am a Wallet Workflow Agent that can mint and send USDC.")
    wallets = {
        "0x111111": Wallet("0x111111"),
        "0x222222": Wallet("0x222222"),
        "0x333333": Wallet("0x333333"),
    }
    agent = WalletWorkflowAgent(
        name="Secure Agent",
        model=model,
        wallets=wallets
    )
    manager = WorkflowManager(verbose=True, managed_context=None)
    chat_history = None
    while True:
        user_input = input("\n\nSample prompt: Have 0x111111 mint 10 USDC to 0x222222 and then have 0x222222 send 5 USDC to 0x333333.\n Ask a question or type 'exit': ")
        if user_input.lower() == 'exit':
            break
        chat_history = await ask_and_respond(agent, user_input, manager, chat_history)

async def run_wallet_instance_agent():
    print("I am a simple agent. I can mint and send USDC.")

    wallets = {
        "0x111111": Wallet("0x111111"),
        "0x222222": Wallet("0x222222"),
        "0x333333": Wallet("0x333333"),
    }

    agent = WalletInstanceAgent(
        name="My Agent",
        model=model,
        wallets=wallets
    )
    manager = None
    chat_history = None
    while True:
        user_input = input("\n\nSample prompt: Have 0x111111 mint 10 USDC to 0x222222 and then have 0x222222 send 5 USDC to 0x333333.\n Ask a question or type 'exit': ")
        if user_input.lower() == 'exit':
            break
        chat_history = await ask_and_respond(agent, user_input, manager, chat_history)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "instance":
        asyncio.run(run_wallet_instance_agent())
    else:
        asyncio.run(run_wallet_workflow_agent())