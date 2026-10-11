"""The tests always run in test mode (fake model), even on a computer where
ANTHROPIC_API_KEY is set or a .env file exists - so running the tests never
calls the real API or costs money.

An empty value (rather than removing the variable) also stops the .env file
from filling it in, because config.py never overwrites a variable that exists.
"""

import os

os.environ["ANTHROPIC_API_KEY"] = ""
