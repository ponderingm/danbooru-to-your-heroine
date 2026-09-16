import json
import os
import sys

sys.path.insert(0, os.path.abspath("src"))
import config
from danbooru_to_heroine import fetch_post, mutate_tags_to_heroine
from multi_subject_adapter import separate_multi_subject_tags

post = fetch_post("7967741")
res = mutate_tags_to_heroine(post, heroine="yukikaze", artist_mode="override")
identity_tags, situation_tags, _ = res[0], res[1], res[2]

separated = separate_multi_subject_tags(situation_tags, identity_tags)
print("=== separated keys and contents ===")
for k, v in separated.items():
    print(f"{k}: {v}")
