Fixture: a cut-down CM5 recipe-engine service (Python 3, standard library only).
Tests: `python3 -m unittest discover -s tests -t .` from this directory.
Known defect used by the backend-engineer evals: `CookingSession.advance()` never finishes a session;
after the last stage the state stays COOKING and `current_stage` raises IndexError.
