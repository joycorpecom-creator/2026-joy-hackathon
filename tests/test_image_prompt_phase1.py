import json

from agent_runtime.image_prompt_compiler import compile_image_prompt
from agent_runtime.image_brief_planner import build_fallback_image_brief
from agent_runtime.prompt_library import build_mockup_prompt, resolve_commercial_intent, resolve_shot_type
from agent_runtime.prompt_quality import score_prompt


def test_fallback_brief_normalizes_black_american_audience():
    brief = build_fallback_image_brief(
        user_scene="nhắm đến khách hàng mỹ cá tính da màu",
        product_name="AOP Unisex Hoodie",
        product_type="AOP Unisex Hoodie - Soft Felt Standard",
        color="black",
        count=2,
    )
    assert "Black" in brief["audience"] or "African American" in brief["audience"]
    assert len(brief["scenes"]) == 2
    assert brief["scenes"][0]["background"] != brief["scenes"][1]["background"]


def test_compiled_prompt_contains_reasoned_brief_and_preservation_rules():
    brief = {
        "audience": "Black / African American customers in the US market",
        "product_category": "apparel_hoodie",
        "creative_direction": "bold streetwear editorial",
        "model": {"ethnicity": "Black / African American", "age_range": "22-35", "style": "urban confident"},
        "scenes": [{"concept": "urban portrait", "background": "clean city wall", "pose": "confident standing pose", "camera": "85mm lens", "lighting": "golden hour", "composition": "hero product centered", "negative": ["no warped print"]}],
        "preservation_rules": ["preserve exact product color", "front design fully visible"],
    }
    prompt = compile_image_prompt(
        brief=brief,
        scene_index=0,
        product_name="AOP Unisex Hoodie",
        product_type="AOP Unisex Hoodie - Soft Felt Standard",
        color="black",
        user_scene="mockup chuyên nghiệp",
    )
    assert "[ROLE & ASSIGNMENT]" in prompt
    assert "Shot type:" in prompt
    assert "Commercial use:" in prompt
    assert "Black / African American" in prompt
    assert "clean city wall" in prompt
    assert "preserve exact product color" in prompt
    assert "REFERENCE PRESERVATION CONTRACT" in prompt
    assert "NEGATIVE CONSTRAINTS" in prompt


def test_default_model_direction_uses_mature_professional_faceless_emotion():
    brief = build_fallback_image_brief(
        user_scene="mockup chuyên nghiệp thần thái mạnh không mặt",
        product_name="AOP Unisex Hoodie",
        product_type="AOP Unisex Hoodie - Soft Felt Standard",
        color="black",
        count=1,
    )
    assert brief["model"]["age_range"] == "24-50"
    assert "professional" in brief["model"]["style"].lower()
    scene = brief["scenes"][0]
    assert "face" in scene["composition"].lower()
    assert "emotion" in scene["pose"].lower()


def test_shot_type_and_commercial_intent_detection():
    assert resolve_shot_type("social ad creative") == "social ad creative"
    assert resolve_commercial_intent("amazon main listing") == "amazon main listing"
    prompt_result = build_mockup_prompt(product_name="T-shirt", product_type="tee", color="black", user_scene="instagram lifestyle")
    assert prompt_result["shot_type"] == "social ad creative"
    assert prompt_result["commercial_intent"] == "instagram square post"
    assert "REFERENCE PRESERVATION CONTRACT" in prompt_result["prompt"]


def test_prompt_qa_scoring():
    good = "[ROLE] Senior photographer. [REFERENCE PRESERVATION CONTRACT] preserve exact design, do not redesign, source of truth. [SCENE] modern café, clean composition, camera 85mm, natural lighting. [PHYSICS] premium cotton fabric texture, realistic folds. [COMMERCIAL] ecommerce listing for shopify, marketplace ready. [NEGATIVE] no distorted print, no extra logos, no warped product, no watermarks."
    qa = score_prompt(good)
    assert qa["risk"] == "low"
    assert qa["overall"] >= 6
    assert not qa["missing"]

    bad = "create an image"
    qa = score_prompt(bad)
    assert qa["risk"] == "high"
    assert qa["missing"]
