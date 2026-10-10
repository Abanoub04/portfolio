"""The agent engine: the loop that every LedgerMind agent runs.

An agent = a model (the brain) + instructions (its job description)
         + tools (normal Python functions it may use) + this loop.

The loop, in plain words:
  1. Give the model its instructions, the task and the list of tools.
  2. The model answers. Either it asks to use one or more tools,
     or it says it is done.
  3. If it asked for tools: run those Python functions, hand the results
     back to the model, and go to step 2.
  4. If it is done: return its final answer.

The model never calculates anything itself. It only decides which tool
to use; the Python function does the actual work.
"""

import json

import config
from agents.models import create_model


class AgentError(Exception):
    """Raised when an agent cannot finish its task."""


class Agent:
    def __init__(self, name, instructions, tools, log, fake_script=None):
        """
        name:         who this agent is, e.g. "Collector" (used in the log)
        instructions: the agent's job description (the "system prompt")
        tools:        list of tool dictionaries, each with
                      name, description, input_schema and function
        log:          the shared ActionLog for this run
        fake_script:  what the agent does in test mode (see FakeModel)
        """
        self.name = name
        self.instructions = instructions
        self.log = log
        self.model = create_model(fake_script)

        # A dictionary from tool name to tool, so a tool can be looked up
        # by the name the model asks for.
        self.tools = {}
        for tool in tools:
            self.tools[tool["name"]] = tool

    def tool_list_for_model(self):
        """The tool descriptions the model sees. The model sees only the
        name, the description and the inputs - never the Python code."""
        tool_list = []
        for tool in self.tools.values():
            tool_list.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            })
        return tool_list

    def run(self, task):
        """Work on a task until done. Returns the agent's final answer."""
        self.log.write(self.name, "START", f"[{self.model.name}] {task}")

        # The conversation so far. It starts with the task and grows
        # with every round of the loop.
        messages = [{"role": "user", "content": task}]

        for step in range(1, config.MAX_STEPS + 1):
            # 1. Ask the model what to do next.
            response = self.model.respond(self.instructions, messages, self.tool_list_for_model())

            # Remember the model's answer as part of the conversation.
            messages.append({"role": "assistant", "content": response.content})

            # 2a. The model wants to use tools: run them and report back.
            if response.stop_reason == "tool_use":
                # Log anything the model said in words alongside its tool calls.
                for block in response.content:
                    if block.type == "text" and block.text.strip():
                        self.log.write(self.name, "SAYS", block.text)

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_results.append(self.use_tool(block, step))

                # All results go back together, in one message.
                messages.append({"role": "user", "content": tool_results})
                continue  # back to the top of the loop

            # 2b. The model is done: collect its final answer.
            if response.stop_reason == "end_turn":
                final_answer = self.final_text(response)
                self.log.write(self.name, "FINISH", final_answer)
                return final_answer

            # 2c. Anything else means something went wrong, for example
            #     the answer was cut off (max_tokens) or refused (refusal).
            self.log.write(self.name, "ERROR", f"Model stopped with reason: {response.stop_reason}")
            raise AgentError(f"{self.name} stopped unexpectedly: {response.stop_reason}")

        # The safety brake: too many rounds without finishing.
        self.log.write(self.name, "ERROR", f"Gave up after {config.MAX_STEPS} steps")
        raise AgentError(f"{self.name} did not finish within {config.MAX_STEPS} steps")

    def use_tool(self, block, step):
        """Run the tool the model asked for and package the result for the model."""
        tool_input = json.dumps(block.input, ensure_ascii=False)
        self.log.write(self.name, "TOOL CALL", f"[step {step}] {block.name} {tool_input}")

        tool = self.tools.get(block.name)
        if tool is None:
            return self.tool_error(block, f"Unknown tool '{block.name}'.")

        try:
            # block.input is a dictionary like {"file_name": "budget.csv"}.
            # The ** turns it into keyword arguments: function(file_name="budget.csv").
            result = tool["function"](**block.input)
        except Exception as error:
            # A failing tool must not crash the company. The error goes back
            # to the model as a message, so it can try something else.
            return self.tool_error(block, f"{type(error).__name__}: {error}")

        # The model reads text, so turn dictionaries and lists into JSON text.
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)

        self.log.write(self.name, "TOOL RESULT", result)
        return {"type": "tool_result", "tool_use_id": block.id, "content": result}

    def tool_error(self, block, message):
        self.log.write(self.name, "TOOL ERROR", message)
        return {"type": "tool_result", "tool_use_id": block.id, "content": message, "is_error": True}

    def final_text(self, response):
        """Join all text blocks of the model's last answer."""
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts).strip()
