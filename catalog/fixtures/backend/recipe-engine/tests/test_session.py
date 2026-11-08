import unittest

from recipe_engine import CookingSession, InvalidTransition, Stage, State

STAGES = [Stage("saute", 160.0, 120), Stage("simmer", 95.0, 600)]


class SessionTransitions(unittest.TestCase):
    def test_start_from_idle(self):
        s = CookingSession(list(STAGES))
        s.start()
        self.assertIs(s.state, State.COOKING)
        self.assertEqual(s.setpoint_c, 160.0)

    def test_pause_only_while_cooking(self):
        s = CookingSession(list(STAGES))
        with self.assertRaises(InvalidTransition):
            s.pause()
        s.start()
        s.pause()
        self.assertIs(s.state, State.PAUSED)
        self.assertEqual(s.setpoint_c, 0.0)

    def test_resume_returns_to_cooking(self):
        s = CookingSession(list(STAGES))
        s.start()
        s.pause()
        s.resume()
        self.assertIs(s.state, State.COOKING)

    def test_advance_moves_to_next_stage(self):
        s = CookingSession(list(STAGES))
        s.start()
        s.advance()
        self.assertEqual(s.current_stage.name, "simmer")
        self.assertEqual(s.setpoint_c, 95.0)

    def test_fault_records_reason(self):
        s = CookingSession(list(STAGES))
        s.start()
        s.fault("pot removed")
        self.assertIs(s.state, State.FAULT)
        self.assertEqual(s.fault_reason, "pot removed")


if __name__ == "__main__":
    unittest.main()
