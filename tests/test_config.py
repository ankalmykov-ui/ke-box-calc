from ke_box_calc.core.config import Settings


def test_staging_environment_and_comma_separated_origins() -> None:
    settings = Settings(
        app_env="staging",
        allowed_origins="https://staging.example, https://admin.staging.example",
    )

    assert settings.app_env == "staging"
    assert settings.allowed_origin_list == [
        "https://staging.example",
        "https://admin.staging.example",
    ]
