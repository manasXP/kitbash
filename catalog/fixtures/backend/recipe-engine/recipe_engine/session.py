"""Cooking session state machine.

The recipe engine drives one session per pot. The STM32 bridge publishes the heater
setpoint for the current stage; the Kivy UI shows the stage name and remaining time.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class State(Enum):
    IDLE = "idle"
    COOKING = "cooking"
    PAUSED = "paused"
    DONE = "done"
    FAULT = "fault"


class InvalidTransition(Exception):
    """Raised when a transition is not allowed from the current state."""


@dataclass(frozen=True)
class Stage:
    name: str
    target_c: float
    seconds: int


@dataclass
class CookingSession:
    stages: List[Stage]
    state: State = State.IDLE
    stage_index: int = 0
    fault_reason: str = ""
    log: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.stages:
            raise ValueError("a session needs at least one stage")

    @property
    def current_stage(self) -> Stage:
        return self.stages[self.stage_index]

    @property
    def setpoint_c(self) -> float:
        """Heater setpoint published to the STM32 bridge; 0 when not cooking."""
        if self.state is State.COOKING:
            return self.current_stage.target_c
        return 0.0

    def start(self) -> None:
        self._require(State.IDLE)
        self.state = State.COOKING
        self.log.append(f"start {self.current_stage.name}")

    def pause(self) -> None:
        self._require(State.COOKING)
        self.state = State.PAUSED
        self.log.append("pause")

    def resume(self) -> None:
        self._require(State.PAUSED)
        self.state = State.COOKING
        self.log.append("resume")

    def advance(self) -> None:
        """Move to the next stage once the current stage's timer has elapsed."""
        self._require(State.COOKING)
        self.stage_index += 1
        self.log.append(f"advance {self.stage_index}")

    def fault(self, reason: str) -> None:
        if self.state in (State.DONE, State.FAULT):
            raise InvalidTransition(f"cannot fault from {self.state.value}")
        self.state = State.FAULT
        self.fault_reason = reason
        self.log.append(f"fault {reason}")

    def _require(self, expected: State) -> None:
        if self.state is not expected:
            raise InvalidTransition(f"expected {expected.value}, session is {self.state.value}")
