#!/usr/bin/env python3
"""Print a style's video prompt with the vehicle and the dealer's local scenery filled in.

  prompt.py heartfelt --vehicle "blue 2026 Honda CR-V Sport Touring" \
            --look "canyon river blue paint, black honeycomb grille, black 19-inch wheels"
"""
import argparse
import json

from common import SKILL, load_dealer

DEFAULT_SCENERY = "a quiet hillside overlook outside town"

ap = argparse.ArgumentParser()
ap.add_argument("style", help="heartfelt | sky-drop | exploded | any other name in styles/")
ap.add_argument("--vehicle", required=True)
ap.add_argument("--look", required=True, help="what makes this exact car recognisable, from the photos")
ap.add_argument("--dealer", help="dealer profile slug; default is the default profile")
ap.add_argument("--scenery", help="override the dealer profile's scenery for this one clip")
a = ap.parse_args()
style = json.loads((SKILL / "styles" / f"{a.style}.json").read_text())
scenery = a.scenery or load_dealer(a.dealer).get("scenery") or DEFAULT_SCENERY
print(style["prompt"].format(vehicle=a.vehicle, look=a.look, scenery=scenery))
