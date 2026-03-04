"""
skills/base_skill.py
Abstract base class for all skills.
Each skill has single responsibility, strict input/output, and is independently testable.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """
    All skills inherit from this.
    - No DB access unless the skill is explicitly persistence-related.
    - No LLM calls in deterministic skills.
    - execute() is the only public interface.
    """

    @abstractmethod
    def execute(self, **kwargs: Any) -> dict:
        """
        Execute the skill logic.
        Args: passed as keyword arguments matching the skill's input schema.
        Returns: dict matching the skill's output schema.
        Raises: ValueError on invalid inputs.
        """
        ...
