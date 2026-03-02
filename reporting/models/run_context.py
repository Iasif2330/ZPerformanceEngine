# reporting/models/run_context.py
from dataclasses import dataclass
from typing import List
from datetime import datetime

@dataclass
class RunContext:
    environment: str
    load_profile: str
    apis: List[str]
    start_ts: datetime
    end_ts: datetime

    @property
    def duration_seconds(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds()