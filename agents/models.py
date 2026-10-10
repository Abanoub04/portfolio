"""The "brain" behind every agent: either the real AI model or a fake one.

- RealModel calls Claude through the Anthropic API. It is used only when
  the ANTHROPIC_API_KEY environment variable is set.
- FakeModel follows a fixed script instead of thinking. It needs no API
  key, costs nothing and always behaves the same, so the engine and the
  logging can be tested offline.

Both have the same method, respond(), and both return an answer with the
same shape. The agent loop therefore does not need to know which one it
is talking to.
"""

import os
from dataclasses import dataclass, field

import config


def using_real_model():
    """True when an API key is available, so the real model can be used."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def create_model(fake_script=None):
    """Return a RealModel if an API key is set, otherwise a FakeModel."""
    if using_real_model():
        return RealModel()
    return FakeModel(fake_script or [])


# ---------------------------------------------------------------------------
# The real model
# ---------------------------------------------------------------------------

class RealModel:
    name = config.MODEL

    def __init__(self):
        # Imported here, so test mode works even without the package installed.
        import anthropic

        # The client reads ANTHROPIC_API_KEY from the environment by itself.
        # The key is never written in any file.
        self.client = anthropic.Anthropic()

    def respond(self, instructions, messages, tools):
        """Send the conversation so far to Claude and return its answer."""
        return self.client.beta.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=instructions,
            messages=messages,
            tools=tools,
            output_config={"effort": config.EFFORT},
            # If Claude declines a request for safety reasons, the API
            # automatically retries it on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )


# ---------------------------------------------------------------------------
# The fake model (test mode)
# ---------------------------------------------------------------------------
# The real API answers with objects that have .stop_reason and .content,
# where content is a list of blocks (text blocks and tool_use blocks).
# These small classes copy that shape, so the agent loop can't tell the
# difference.

@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeResponse:
    stop_reason: str
    content: list = field(default_factory=list)


class FakeModel:
    """Plays back a script, one step per call.

    A script is a list of steps. Each step is either
        {"tool": "tool_name", "input": {...}}   -> ask to use a tool
        {"text": "final answer"}                -> finish with this answer
    """

    name = "fake model (test mode)"

    def __init__(self, script):
        self.script = list(script)
        self.step_number = 0
        # Every conversation the fake model receives is kept here,
        # so tests can check that tool results were passed back correctly.
        self.received = []

    def respond(self, instructions, messages, tools):
        self.received.append(list(messages))

        # When the script runs out, finish politely.
        if self.step_number >= len(self.script):
            return FakeResponse("end_turn", [FakeTextBlock("(fake model) Script finished.")])

        step = self.script[self.step_number]
        self.step_number += 1

        if "tool" in step:
            block = FakeToolUseBlock(
                id=f"fake_call_{self.step_number}",
                name=step["tool"],
                input=step.get("input", {}),
            )
            return FakeResponse("tool_use", [block])

        return FakeResponse("end_turn", [FakeTextBlock(step["text"])])
