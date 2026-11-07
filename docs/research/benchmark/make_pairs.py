"""
Build the blind forced-choice files for the description benchmark.

    python make_pairs.py REAL.json GENERATED.yaml OUT_DIR [--seed 11]

REAL.json is a list of {"initiative": <heading>, "author": ..., "text": ...}.
GENERATED.yaml is a suggestions file whose `initiatives:` carry the same names.
Writes OUT_DIR/pairs-raw.json and pairs-flat.json, which go to the blind agent,
and OUT_DIR/pairs-key.json, which does not. `flat` removes layout, so a verdict
cannot rest on bullets or paragraph count.
"""
import argparse
import json
import random
import re

import yaml


def flatten(text):
    text = re.sub(r"^\s*[-•*]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("real")
    parser.add_argument("generated")
    parser.add_argument("out")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    real = {r["initiative"]: r for r in json.load(open(args.real, encoding="utf-8"))}
    generated = {g["name"]: str(g["description"]).strip() for g in
                 yaml.safe_load(open(args.generated, encoding="utf-8"))["initiatives"]}
    assert set(real) == set(generated), set(real) ^ set(generated)

    rng = random.Random(args.seed)
    raw, flat, key = [], [], {}
    for n, name in enumerate(sorted(real), 1):
        sides = [("real", real[name]["text"]), ("generated", generated[name])]
        rng.shuffle(sides)
        # The heading minus its parenthetical, which can give a side away.
        short = re.sub(r"\s*\(.*", "", name)
        raw.append({"pair": f"Q{n}", "initiative": short,
                    "A": sides[0][1], "B": sides[1][1]})
        flat.append({"pair": f"Q{n}", "initiative": short,
                     "A": flatten(sides[0][1]), "B": flatten(sides[1][1])})
        key[f"Q{n}"] = {"A": sides[0][0], "B": sides[1][0]}

    for name, data in (("pairs-raw", raw), ("pairs-flat", flat), ("pairs-key", key)):
        with open(f"{args.out}/{name}.json", "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
