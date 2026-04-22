import re


def _replace_remaining_placeholders(code: str) -> str:
    # Match placeholders while avoiding those inside quotes
    pattern = re.compile(r'("[^"]*"|\'[^\']*\'|\{\{[A-Z_]+:.*?\}\})', re.DOTALL)
    output_lines = []
    for line in code.splitlines():
        if "{{" not in line:
            output_lines.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        the_content = line.strip()

        def _handle_match(m):
            text = m.group(1)
            if text.startswith(('"', "'")):
                return text
            return f'pytest.skip("Placeholder could not be resolved: {text}")'

        new_content = pattern.sub(_handle_match, the_content)
        output_lines.append(f"{indent}{new_content}")
    return "\n".join(output_lines)


# Test cases
code1 = "evidence_tracker.click('sel', label='{{CLICK:basket}}')"
code2 = "def test():\n    {{ASSERT:success}}"

print(f"Case 1: {code1}")
print(f"Result 1: {_replace_remaining_placeholders(code1)}")
print(f"Case 2:\n{code2}")
print(f"Result 2:\n{_replace_remaining_placeholders(code2)}")
