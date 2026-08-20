"""Тесты локального фолбэка генерации промптов.

Запуск без pytest: python3 tests/test_prompt_fallback.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.services.prompt_fallback import (  # noqa: E402
    GENDERS,
    STYLES,
    build_local_prompt,
)

ALL_COMBOS = [(g, s) for g in GENDERS for s in STYLES]


def test_returns_non_empty_prompt_for_every_gender_style_combo():
    for gender, style in ALL_COMBOS:
        prompt = build_local_prompt(gender, style)
        assert len(prompt) > 200, f"too short for {gender}/{style}: {prompt}"


def test_prompt_starts_with_photorealism_marker():
    for gender, style in ALL_COMBOS:
        prompt = build_local_prompt(gender, style)
        assert prompt.startswith("RAW photo, 8K UHD, DSLR"), prompt[:60]


def test_prompt_names_the_correct_subject_gender():
    assert "portrait of a man in his " in build_local_prompt("male", "casual")
    assert "portrait of a woman in her " in build_local_prompt("female", "casual")


def test_subject_phrase_is_grammatical():
    for gender, style in ALL_COMBOS:
        prompt = build_local_prompt(gender, style)
        assert "of a in " not in prompt, prompt[:120]
        assert " s wearing" not in prompt, prompt[:120]


def test_prompts_vary_between_calls():
    generated = {build_local_prompt("male", "business") for _ in range(30)}
    assert len(generated) > 10, f"only {len(generated)} unique of 30"


def test_business_style_uses_business_wardrobe():
    prompts = " ".join(build_local_prompt("male", "business") for _ in range(30))
    assert "suit" in prompts or "blazer" in prompts
    assert "hoodie" not in prompts


def test_casual_style_avoids_formal_wardrobe():
    prompts = " ".join(build_local_prompt("female", "casual") for _ in range(30))
    assert "suit" not in prompts
    assert "tuxedo" not in prompts


def test_unknown_gender_and_style_fall_back_without_raising():
    prompt = build_local_prompt("unknown", "nonsense")
    assert prompt.startswith("RAW photo, 8K UHD, DSLR")
    assert len(prompt) > 200


def test_prompt_requests_photorealistic_skin_and_hair_detail():
    prompt = build_local_prompt("female", "creative")
    lowered = prompt.lower()
    assert "pores" in lowered
    assert "hair strands" in lowered


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"\n{'FAILED' if failures else 'OK'} — {failures} failure(s)")
    sys.exit(1 if failures else 0)
