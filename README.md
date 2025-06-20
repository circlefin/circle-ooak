# Circle LOOFA: Lightweight Object-Oriented Framework for Agents

## License
This work is licensed under Apache 2.0. see SPDX-License-Identifier in the file headings.

`SPDX-License-Identifier: Apache-2.0`

It has not been audited, comes with
no guarantees, and is provided as is. Use at your own risk.

## Introduction
This project creates an extension to the OpenAI Agents SDK.

- The `@agent_tool` decorator can be used with object instance methods instead of `@function_tool` which only
supports static functions. 
- The `@secure_tool` decorator  can be used instead of the `@agent_tool` decorator
to add before/after hooks to your tool code.
- An `InstanceAgent` that can use `@agent_tool` and `@secure_tool`. An `InstanceAgent` is a subclass of
a regular `Agent` and can interact with other agents via handoffs and guardrails.


We implemented a Workflow Manager that implements the abstract `SecurityContext`,
that checks that intended actions have been approved.

1. Create intent. The agent calls the @secure_tool function with `wfid=None` argument. Instead of
executing the function, it returns an intent: a json representation of the function call.
2. Get Approval. The agent calls the WorkflowManager with a list of intents. The WorkflowManager
approves the list of intents and returns a WorkflowId.
3. Execute. The agent now calls the @secure_tools in the correct order with the WorkflowId. The
WorkflowManager ensures that each subsequent function call matches the approved workflow.

```python
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

    @function_tool
    def approve_workflow(ctxt: RunContextWrapper[WorkflowManager], workflow: list[str]):
        """Approve a workflow of secure tool calls.
        workflow: a list of intents (json strings).
        returns: a string with the workflow id
        """
        manager = ctxt.context
        response = manager.approve(workflow)
        if response.approved:
            return f"Workflow approved: with wfid {response.msg}"
        else:
            return f"Workflow not approved: {response.msg}"

    @secure_tool
    def send_usdc(self, ctxt: RunContextWrapper[WorkflowManager], wfid: str, sender: str, receiver: str, amount: int):
        wallet = self.wallets[sender]
        if wallet is None:
            return f"Wallet {sender} not found"
        return wallet.send_usdc(receiver, amount)

# Sample agent
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
```

You can look at model code in the file `wallet_agent.py`.

## Setup Python environment
You will need Python. 

Create a virtual environment and install requirements:
```shell
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```

Activate your virtual environment
```shell
source .venv/bin/activate
```

Decativate your virtual environment
```shell
deactivate
```

## Setup LLM
Create an `.env` file. You must obtain an OpenAI API key.

```shell
# External: get API key from https://platform.openai.com/api-keys
OPENAI_API_KEY=api_key_goes_here

# URL to connect to OpenAI
OPENAI_URL=https://api.openai.com/v1/models

# OpenAI model to use
OPENAI_MODEL=gpt-4o
```

## Run demo
All agents are defined in the file `wallet_agent.py`. To test them, 
activate the virtual environment and run the `simple_agent.py` program.

```shell
# To run a Wallet Workflow Agent 
cd src
python run_agent.py 

# To run a Wallet Instance Agent 
cd src
python run_agent.py instance

# To run unit tests
cd src
python model_unit_test.py
```

Here is sample output from one run:

```shell
  Ask a question or type 'exit': Have 0x111111 mint 10 USDC to 0x222222 and then have 0x222222 send 5 USDC to 0x333333.

LOG: Approving workflow with intents: ['{"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"}', '{"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"}']
LOG: Approved workflow f0082344-018c-4d5c-856a-fb8989ab6bf2 with intents: [{"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"}, {"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"}].
Override this method with your own approval logic.

LOG: Starting action {"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"}
Minting 10 USDC by 0x111111 to 0x222222
LOG: Finished action {"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"} with result txhash=0987654321

LOG: Starting action {"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"}
Sending 5 USDC from 0x222222 to 0x333333
LOG: Finished action {"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"} with result txhash=1234567890

LOG: Workflow completed successfully with result txhash=1234567890
The transactions were successfully executed. Here are the transaction hashes:

1. Mint 10 USDC from `0x111111` to `0x222222`: `txhash=0987654321`
2. Send 5 USDC from `0x222222` to `0x333333`: `txhash=1234567890`

```

## Dev notes
Functions decorated with `@secure_tool` must include the following two arguments:
- `wfid: WorkflowId`. Agents will use the workflow id to get permission to perform tasks.
- `ctxt: RunContextWrapper[SecurityContext]`. The runner must provide an object as context that
implements the abstract class `SecurityContext` such as the `WorkflowManager` included in this project.


Agent tools with the `@secure_tool` or `@agent_tool` decorators can be tested the same way as those with `@function_tool`.
We include a model unit test file.

```shell
python model_unit_test.py
```
