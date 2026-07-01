# Circle OOAK: Object-Oriented Agent Kit

## License
This work is licensed under Apache 2.0. See SPDX-License-Identifier in the file headings.

`SPDX-License-Identifier: Apache-2.0`

It has not been audited, comes with
no guarantees, and is provided as is. Use at your own risk.

## Introduction
This project creates an extension to the OpenAI Agents SDK.

- The `@agent_tool` decorator can be used with object instance methods instead of `@function_tool` which only
supports static functions. 
- The `@secure_tool` decorator can be used instead of the `@agent_tool` decorator
to add before/after hooks to your tool code. 
- An `InstanceAgent` subclass that can use `@agent_tool` and `@secure_tool`. An `InstanceAgent` is a subclass of
a regular OpenAI Agents SDK `Agent` and can interact with other agents via handoffs and guardrails.


This package includes a `WorkflowManager` that implements the abstract `SecureContext`,
that checks that intended actions have been approved.

1. Create intent. The agent calls the @secure_tool function with `wfid=None` argument. Instead of
executing the function, it returns an intent: a JSON representation of the function call.
2. Get approval. The agent calls the WorkflowManager with a list of intents. The manager invokes `get_approval()` (which you override to connect your UX or policy) and, if approved, returns a `wfid`.
3. Execute. The agent now calls the @secure_tools in the correct order with the `wfid`. The
WorkflowManager ensures that each subsequent function call matches the approved workflow.

Sample code can be found at https://github.com/circlefin/circle-ooak/tree/master/example

Below is an example of a `WalletWorkflowAgent`.

```python
from agents import function_tool, RunContextWrapper, OpenAIChatCompletionsModel
from circle_ooak.instance_agent import InstanceAgent
from circle_ooak.secure_tool import secure_tool
from circle_ooak.workflow_manager import WorkflowManager

class WalletWorkflowAgent(InstanceAgent):
    instructions = """
    You help users execute Ethereum transactions. Do the following steps to help the user:
    1. Create a workflow of intents by calling each secure tool with wfid=None to get the intents
    2. Call approve_workflow with the list of intents to get a wfid
    3. Execute the workflow by calling each secure tool again. You MUST include the wfid parameter with the wfid you got in step 2.
    4. Print the final tx hash for every transaction.
    
    You do not need approval from the user to execute a workflow if you have the wfid.
    """
    def __init__(self, name: str, model: OpenAIChatCompletionsModel, wallets: dict[str, Wallet]):
        self.wallets = wallets
        tools = [self.approve_workflow]
        agent_tools = [self.send_usdc, self.mint_usdc]
        super().__init__(name=name, instructions=self.instructions, model=model, tools=tools, agent_tools=agent_tools)

    @function_tool
    def approve_workflow(ctxt: RunContextWrapper[WorkflowManager], workflow: list[str]):
        """Approve a workflow of secure tool calls.
        workflow: a list of intents (JSON strings).
        returns: a string with the wfid
        """
        manager = ctxt.context
        response = manager.approve(workflow)
        if response.approved:
            return f"Workflow approved: with wfid {response.msg}"
        else:
            return f"Workflow not approved: {response.msg}"

    @secure_tool
    def send_usdc(self, ctxt: RunContextWrapper[WorkflowManager], sender: str, receiver: str, amount: int):
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

## Approval logic

OOAK is a framework: it handles intent capture, workflow state, and **enforcement** (each `@secure_tool` call must match the approved plan). It does **not** include a production approval UI or policy engine.

**You must connect your own UX and rules** by subclassing `WorkflowManager` and overriding `get_approval()`. The default implementation auto-approves every workflow so the demo runs without extra setup.

Example:

```python
from circle_ooak.workflow_manager import WorkflowManager, ManagerResponse

class MyWorkflowManager(WorkflowManager):
    def __init__(self, approval_client, verbose: bool = False):
        super().__init__(verbose=verbose)
        self.approval_client = approval_client

    def get_approval(self, workflow) -> ManagerResponse:
        # Present workflow.actions to your UI or policy service.
        # Each action.intent is JSON: function, arguments, and optional instance.
        approved = self.approval_client.request_user_signoff(
            wfid=workflow.wfid,
            intents=[action.intent for action in workflow.actions],
        )
        if approved:
            return ManagerResponse(True, "Approved")
        return ManagerResponse(False, "User rejected workflow")
```

Pass your subclass as the runner context (as in `example/run_agent.py`):

```python
manager = MyWorkflowManager(approval_client=client, verbose=True)
result = await Runner.run(agent, question, context=manager)
```

After approval, `WorkflowManager` ensures execution matches the stored intents (tool name, arguments, order) at **start** time. Your `get_approval()` implementation decides **whether** a workflow may run; the manager **enforces** your approvals.

`approve()` validates intent shape (JSON structure and allowed keys). It does not require intents to come from a particular tool call — what matters is the **content** of each intent and whether your user or policy approves it in `get_approval()`.


## Setup Python environment
Install the `circle-ooak` package and other dependencies:

```shell
pip install circle-ooak
pip install python-dotenv openai openai-agents
```

Alternatively, you can clone the GitHub Repo and install using 
the `requirements.txt` file:
```shell
git clone http://github.com/circlefin/circle-ooak
cd circle-ooak
pip install -r requirements.txt
pip install circle-ooak
```

We recommend you use a virtual environment:
```shell
# create an environment
python -m venv .venv

# activate the environment
source .venv/bin/activate

# deactivate the environment
deactivate
```

## Setup Environment
Create an `.env` file. You must obtain an OpenAI API key.

```shell
# External: get API key from https://platform.openai.com/api-keys
OPENAI_API_KEY=api_key_goes_here

# URL to connect to OpenAI
OPENAI_URL=https://api.openai.com/v1

# OpenAI model to use
OPENAI_MODEL=gpt-4o
```

## Run demo
You must setup your LLM using the `.env` file to run the demo.

```shell
# Download demo
git clone http://github.com/circlefin/circle-ooak
cd circle-ooak
pip install -r requirements.txt
pip install circle-ooak

# To run a Wallet Workflow Agent 
python example/run_agent.py

# To run a Wallet Instance Agent 
python example/run_agent.py instance

# To run unit tests
python -m pytest test/model_unit_test.py -v
```

Here is sample output from one run:

```shell
Have 0x111111 mint 10 USDC to 0x222222 and then have 0x222222 send 5 USDC to 0x333333

LOG: Approving workflow with intents: ['{"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"}', '{"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"}']
LOG: Approved workflow e4aef3b4-2e32-47a4-a004-02b755dd62af with intents: [{"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"}, {"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"}].
Override this method with your own approval logic.

LOG: Starting action {"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"}
Minting 10 USDC by 0x111111 to 0x222222
LOG: Finished action {"function": "mint_usdc", "arguments": {"minter": "0x111111", "receiver": "0x222222", "amount": 10}, "instance": "Secure Agent"} with result txhash=0987654321

LOG: Starting action {"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"}
Sending 5 USDC from 0x222222 to 0x333333
LOG: Finished action {"function": "send_usdc", "arguments": {"sender": "0x222222", "receiver": "0x333333", "amount": 5}, "instance": "Secure Agent"} with result txhash=1234567890

LOG: Workflow completed successfully with result txhash=1234567890
The transactions have been successfully executed:

1. Minting 10 USDC from 0x111111 to 0x222222 was successful with transaction hash: `0987654321`.
2. Sending 5 USDC from 0x222222 to 0x333333 was successful with transaction hash: `1234567890`.

```

## Dev notes
Functions decorated with `@secure_tool` on an `InstanceAgent` should include `ctxt: RunContextWrapper[SecureContext]` when they need the workflow context. The runner must provide an object that implements `SecureContext` (for example `WorkflowManager`).

OOAK uses a workflow id `wfid` to manage approvals. Do **not** include `wfid` in your Python function signature. Authorization metadata stays in the secure wrapper; your handler only receives arguments in the original function definition.


For production use, subclass `WorkflowManager` and override `get_approval()`.
You may also implement a custom `SecureContext` if you need different before/after hooks than the built-in workflow state machine.

The included `WorkflowManager` is a **reference implementation** for demos and testing. It keeps approved workflows in memory for the life of the process. Production systems should subclass it for persistence, audit logs, branching logic, or other lifecycle needs.

### Start, complete, and fail

Each `@secure_tool` execution with a `wfid` uses three hooks:

| Hook | Role |
|------|------|
| `before_invoke_tool` / `start()` | **Authorization** — verify the call matches the approved intent for the current step before the handler runs |
| Handler | Your business logic |
| `after_invoke_tool` / `complete()` | **Record success** — store the handler result and advance workflow state. Does not re-authorize; the handler already ran |
| `on_invoke_tool_failure` / `fail()` | **Record failure** — best-effort transition to `failed` after a handler exception. Always succeeds; it must not leave the workflow stuck |

### Instance identity in intents
OOAK needs a way to uniquely identify agents for approval. There are two choices:
- **by name**. When an `InstanceAgent` is initialized with `bind_to_instance=False`, then OOAK identifies the agent using the `name` supplied during object creation. This creates a stable name across restarts.
- **by object reference**. When an `InstanceAgent` is initialized with `bind_to_instance=True`, then OOAK identifies the agent
using the run-time object identifier. This prevents any naming collisions. Agents have new ids after every restart. 

### Side effects and workflow state

OOAK calls `before_invoke_tool` (start) **before** your handler runs, and `after_invoke_tool` (complete) **after** it returns. If your handler performs an irreversible side effect (transfer funds, sign a transaction, call an external API) and then crashes or hangs, OOAK will not know the outcome of the action. It also will not know how to clean up.

**What OOAK does:** the handler call is wrapped in a try/except. If the handler raises, `@secure_tool` calls `on_invoke_tool_failure`, which marks the current action and workflow as `failed`. This prevents a stuck `in_progress` state. It does **not** roll back side effects that already occurred before the exception.

**What integrators should do:**

- **Compensating tools** — write tools that perform their own cleanup on failure (refund, cancel reservation, revert a pending state). 
- **Two-phase operations** — separate "prepare" and "commit" into different tools or workflow steps so approval covers each phase explicitly.
- **Custom workflow logic** — subclass `WorkflowManager` or implement `SecureContext` with branching based on reported results (a decision tree), rather than assuming a fixed linear sequence, when your use case requires it.

**Handler hangs and infinite loops:** OOAK does not enforce timeouts on tool handlers. A handler that never returns leaves the workflow step in `in_progress` indefinitely. Use `asyncio.wait_for`, application-level deadlines, or runner/SDK limits in your tool implementations and hosting environment.

### Testing
Agent tools with the `@secure_tool` or `@agent_tool` decorators can be tested the same way as those with `@function_tool`.
We include a model unit test file. Unit tests do not require an LLM.

```shell
python -m pytest test/model_unit_test.py -v
```
