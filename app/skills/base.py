from abc import ABC, abstractmethod
from typing import Any


class BaseSkill(ABC):
    """技能基类 - 所有技能都应继承此类"""

    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """
        执行技能

        Args:
            **kwargs: 技能输入参数

        Returns:
            技能执行结果
        """
        raise NotImplementedError
