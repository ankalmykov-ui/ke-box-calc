from ke_box_calc.core.config import Settings


def test_vercel_preview_environment_and_comma_separated_origins() -> None:
    settings = Settings(
        app_env="preview",
        allowed_origins="https://preview.example, https://staging.example",
    )

    assert settings.app_env == "preview"
    assert settings.allowed_origin_list == [
        "https://preview.example",
        "https://staging.example",
    ]
