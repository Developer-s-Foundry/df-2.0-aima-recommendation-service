from abc import ABC, abstractmethod
from typing import Dict, List

class RulePack(ABC):
    @abstractmethod
    def supports(self, event_type: str) -> bool: ...
    @abstractmethod
    def evaluate(self, event: Dict) -> List[str]: ...
