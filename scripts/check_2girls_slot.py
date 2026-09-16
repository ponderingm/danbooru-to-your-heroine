import os
import sys

sys.path.insert(0, os.path.abspath("src"))
from tag_classifier import classifier

for t in ["2girls", "multiple girls", "1girl", "yuri"]:
    s = classifier.classify_tags([t])
    print(f"{t} -> {s.get(t)}")
