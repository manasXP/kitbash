Fixtures for the recipe-author agent.
- `transcripts/kanda-poha.txt`: the real caption track of a YouTube Kanda Poha video (HomeCookingShow, 304 s), fetched
  with `tools/cli/yt_transcript.py` on 2 Nov 2026; convertible to the device format.
- `transcripts/medu-vada.txt`: hand-written in caption style, not a real video. Needs soaking, grinding, hand-shaping and
  deep frying, none of which the robot can do; the agent must say so and write no recipe.
- `existing/`: copies of the five device recipes from epicura-cm5/services/recipe-engine/recipes on 2 Nov 2026, so an
  eval can check dispenser assignments against the project's convention without the repo.
- `out/`: where the evals write new recipe YAML (declared with `creates:` so the path must not exist beforehand).
Validation uses the real engine through `tools/cli/recipe_validate.py` (EPICURA_RECIPE_ENGINE points at the checkout).
