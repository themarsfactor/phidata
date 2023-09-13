from typing import Optional, Any, Dict, Callable, get_type_hints
from pydantic import BaseModel, validate_call

from phi.utils.log import logger


class Message(BaseModel):
    """Pydantic model for holding LLM messages"""

    # The role of the messages author.
    # One of system, user, assistant, or function.
    role: str
    # The contents of the message. content is required for all messages,
    # and may be null for assistant messages with function calls.
    content: Optional[str] = None
    # The name of the author of this message. name is required if role is function,
    # and it should be the name of the function whose response is in the content.
    # May contain a-z, A-Z, 0-9, and underscores, with a maximum length of 64 characters.
    name: Optional[str] = None
    # The name and arguments of a function that should be called, as generated by the model.
    function_call: Optional[Any] = None
    # Metrics for the message, tokes + the time it took to generate the response.
    metrics: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        _dict = self.model_dump(exclude_none=True, exclude={"metrics"})
        # Manually add the content field if it is None
        if self.content is None:
            _dict["content"] = None
        return _dict

    def log(self, level: Optional[str] = None):
        """Log the message to the console

        @param level: The level to log the message at. One of debug, info, warning, or error.
            Defaults to debug.
        """
        _logger = logger.debug
        if level == "debug":
            _logger = logger.debug
        elif level == "info":
            _logger = logger.info
        elif level == "warning":
            _logger = logger.warning
        elif level == "error":
            _logger = logger.error

        if self.role == "function":
            _logger(f"{self.role.upper()}: {self.name}")
            _logger(f"{self.content}")
        else:
            _logger(f"{self.role.upper()}: {self.content or self.function_call}")


class References(BaseModel):
    """Pydantic model for holding LLM references"""

    # The question asked by the user.
    query: str
    # The references from the vector database.
    references: str
    # Performance in seconds.
    time: Optional[float] = None


class Function(BaseModel):
    """Pydantic model for holding LLM functions"""

    # The name of the function to be called.
    # Must be a-z, A-Z, 0-9, or contain underscores and dashes, with a maximum length of 64.
    name: str
    # A description of what the function does, used by the model to choose when and how to call the function.
    description: Optional[str] = None
    # The parameters the functions accepts, described as a JSON Schema object.
    # To describe a function that accepts no parameters, provide the value {"type": "object", "properties": {}}.
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}
    entrypoint: Optional[Callable] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude={"entrypoint"})

    @classmethod
    def from_callable(cls, c: Callable) -> "Function":
        from inspect import getdoc
        from phi.utils.json_schema import get_json_schema

        parameters = {"type": "object", "properties": {}}
        try:
            type_hints = get_type_hints(c)
            parameters = get_json_schema(type_hints)
            # logger.debug(f"Type hints for {c.__name__}: {type_hints}")
        except Exception as e:
            logger.warning(f"Could not parse args for {c.__name__}: {e}")

        return cls(
            name=c.__name__,
            description=getdoc(c),
            parameters=parameters,
            entrypoint=validate_call(c),
        )


class FunctionCall(BaseModel):
    """Pydantic model for holding LLM function calls"""

    # The function to be called.
    function: Function
    # The arguments to call the function with.
    arguments: Optional[Dict[str, Any]] = None
    # The result of the function call.
    result: Optional[Any] = None

    def get_call_str(self) -> str:
        """Returns a string representation of the function call."""
        if self.arguments is None:
            return f"{self.function.name}()"
        return f"{self.function.name}({', '.join([f'{k}={v}' for k, v in self.arguments.items()])})"

    def run(self) -> bool:
        """Runs the function call.

        @return: True if the function call was successful, False otherwise.
        """
        if self.function.entrypoint is None:
            return False

        logger.debug(f"Running: {self.get_call_str()}")

        # Call the function with no arguments if none are provided.
        if self.arguments is None:
            try:
                self.result = self.function.entrypoint()
                return True
            except Exception as e:
                logger.warning(f"Could not run function {self.get_call_str()}: {e}")
                return False

        # Validate the arguments if provided.
        # try:
        #     from jsonschema import validate
        # except ImportError:
        #     raise ImportError("`jsonschema` is required for LLM functions, install using `pip install jsonschema`")
        try:
            self.result = self.function.entrypoint(**self.arguments)
            return True
        except Exception as e:
            logger.warning(f"Could not run function {self.get_call_str()}")
            logger.error(e)
            return False
