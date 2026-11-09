---
name: recipe-authoring
description: Turn a human recipe (video transcript, web page or text) into an Epicura device recipe YAML that the recipe engine validates, with the user's pre-prep spelled out and infeasible steps refused.
requires:
  tools: [Read, Write, Bash]
  capabilities: [video-transcript, recipe-validation]
---
# Recipe authoring for the Epicura device

The device cooks one pot. It can heat the pot surface (30 to 250 °C), stir with a fixed set of
patterns, dispense from three dispensers, wait, and watch the pot with a camera. Everything
else is done by the user before cooking starts.

## Getting the source

- A URL: run `${KITBASH_PYTHON} "${KITBASH_CATALOG}/tools/cli/yt_transcript.py" URL --out transcript.txt`.
  Exit 2 means no caption track and exit
  3 means the fetch failed (unavailable video, rate limit, no network). In both cases stop,
  quote the error, write no recipe, and say what the user can supply instead. Never
  reconstruct a recipe from memory of a video you could not read.
- A transcript or text file: read it whole. Captions are noisy (misheard words, no
  punctuation); resolve ingredient names from context and say when you guessed.

## The device format (the only target)

Top level: `name`, `servings` (1 to 10), `total_time_minutes`, `category` (one of dal, curry, rice,
khichdi, snack, breakfast, biryani, soup), `cuisine` (list from indian, south_indian,
north_indian, gujarati, maharashtrian), `tags`, `difficulty` (easy, medium, hard), `stages`
(1 to 20). Each stage has `name` and `action`:

| action | required | optional |
|---|---|---|
| heat | temp_target 30 to 250 | duration_seconds, stir + stir_pattern |
| stir | | duration_seconds, stir: true + stir_pattern |
| dispense | ingredients (at least one) | |
| wait | duration_seconds | |
| detect_stage | cv_check (a label such as onion_golden, onion_translucent, cumin_splutter) | duration_seconds as the timeout |

`stir_pattern` is one of continuous, intermittent, reverse, scrape, fold and needs `stir: true`.

Dispensers, one per ingredient:

- **ASD** (spice boxes 1 to 6): `asd_box_id`, `amount_g`. Dry ground or whole spices only.
  Keep the project's box convention: 1 cumin seeds, 2 mustard seeds, 3 turmeric,
  4 red chili powder, 5 salt, 6 urad dal. Read the existing recipes beside the output
  before assigning; a spice not in the convention takes a free box and is flagged in the report.
- **CID** (trays 1 and 2): `cid_tray_id`, `mode` FULL or PARTIAL. Chopped vegetables,
  soaked grains and dal, mixes the user prepares. Two trays only, so combine what is added
  together (onion-tomato mix) and refuse a recipe needing more than two separately timed additions.
- **SLD**: `channel` OIL or WATER with `amount_ml`. Nothing else is liquid-dispensed; ghee,
  milk, coconut milk or stock go in a CID tray or make the recipe infeasible.

Quantities: convert spoons to grams (1 tsp of a ground spice is about 2.5 g, of whole seeds about
2 g, of salt 6 g; 1 tbsp oil is 15 ml; 1 cup water is 240 ml) and scale to the servings you declare.

## Mapping human steps to stages

1. List the ingredients and when each is added, then the heat and stir of each step.
2. A step that heats before anything is added becomes `heat` (oil preheat 170 to 180 °C).
   Sautéing is `heat` 150 to 170 °C with stir; simmering 95 to 110 °C; pressure or long
   cooking 115 to 125 °C with the lid assumed closed; "low flame" is 100 to 120 °C.
3. Every addition is a `dispense` stage; cooking after it is a separate `heat` stage with its
   duration and stir pattern (fold for delicate rice or poha, intermittent for onions,
   continuous for sauces, scrape for things that stick).
4. "Until golden", "until translucent", "until seeds splutter" become `detect_stage` with a
   timeout when a matching cv label exists; otherwise use the time the source gives.
5. Finish with a `wait` or a final `stir` where the source rests or mixes.
6. Keep `total_time_minutes` consistent with the stage durations plus dispensing.

## Infeasible steps

The robot cannot: deep fry (an oil bath), grind or blend, knead, roll or shape, bake or grill,
soak or marinate during the session, add more than two prepared tray items, handle garnish or
plating, or control a second vessel. A recipe whose core depends on these is refused: write no YAML,
name each infeasible step with its timestamp or line, and say what a user could do by hand
beforehand if that would make it feasible. Soaking, chopping, grinding a paste and pre-mixing
are allowed as **pre-prep** and go in the report, never in the stages.

## Validation and reporting

Run `${KITBASH_PYTHON} "${KITBASH_CATALOG}/tools/cli/recipe_validate.py" FILE` on every file you write and fix every
error it prints before reporting. Report, in this order: the file path and the validator's
VALID line; the pre-prep list per tray and box (what the user loads where); every guess
(quantity, temperature, box assignment, misheard ingredient); every step left out and why.
A recipe is reported as ready only when the validator printed VALID.
