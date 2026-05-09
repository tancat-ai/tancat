from src.skeleton_parser import SkeletonParser
from src.llm_client import LLMClient

code = open("scratch_raw_out.txt", encoding="utf-8").read()
code = LLMClient()._extract_code(code)
parser = SkeletonParser()
code = parser.normalise_placeholder_actions(code)
journeys = parser.parse_test_journeys(code)

for j in journeys:
    print(f"Journey: {j.test_name}")
    for step in j.steps:
        for p in step.placeholders:
            print(f"  Placeholder: {p.token}")
