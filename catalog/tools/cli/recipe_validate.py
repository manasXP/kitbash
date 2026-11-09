#!/usr/bin/env python3
"""Validate Epicura device recipe YAML files with the recipe engine's own parser.

    recipe_validate.py FILE [FILE ...]

Imports `epicura_recipe` from the checked-out engine (EPICURA_RECIPE_ENGINE, default
~/code/Epicura/epicura-cm5/services/recipe-engine) so the rules are exactly the
device's: pydantic schema, action and dispenser constraints, line-numbered errors.
Prints one line per file. Exit 0 when every file is valid, 5 when any is invalid
(a gate for playbook handoffs), 2 when the engine cannot be imported.
Run with an interpreter that has pydantic and PyYAML; tools/cli/recipe-validator.yaml uses KITBASH_PYTHON.
"""
import os
import sys

ENGINE = os.environ.get("EPICURA_RECIPE_ENGINE",
                        os.path.expanduser("~/code/Epicura/epicura-cm5/services/recipe-engine"))


def main(paths):
    if not paths:
        print(__doc__)
        return 2
    sys.path.insert(0, ENGINE)
    try:
        from epicura_recipe.parser import parse_recipe_file
        from epicura_recipe.errors import RecipeParseError
    except ImportError as exc:
        sys.stderr.write(f"recipe_validate: cannot import the recipe engine from {ENGINE}: {exc}\n")
        return 2
    bad = 0
    for p in paths:
        try:
            r = parse_recipe_file(p)
        except RecipeParseError as exc:
            bad += 1
            print(f"INVALID {p}")
            for e in exc.errors:
                where = f" (line {e.line})" if getattr(e, "line", None) else ""
                print(f"  {e.field_path or '<root>'}{where}: {e.message}")
        except (OSError, Exception) as exc:  # unreadable file or YAML the engine does not wrap
            bad += 1
            print(f"INVALID {p}\n  {exc}")
        else:
            print(f"VALID {p}: {r.name}, {len(r.stages)} stages, {r.total_time_minutes} min, "
                  f"servings {r.servings}, category {r.category}")
    return 5 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
