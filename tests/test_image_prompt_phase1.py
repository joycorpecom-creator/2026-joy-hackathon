import json

from agent_runtime.image_prompt_compiler import compile_image_prompt
from agent_runtime.image_brief_planner import build_fallback_image_brief


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
    assert "ROLE:" in prompt
    assert "Black / African American" in prompt
    assert "clean city wall" in prompt
    assert "preserve exact product color" in prompt
    assert "No redesign" in prompt


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
