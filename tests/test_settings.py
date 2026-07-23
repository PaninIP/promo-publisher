import unittest

from app.settings import (
    RemoteConfigError,
    RuntimeSettings,
    apply_remote_overrides,
    parse_remote_config_text,
)


DEFAULTS = RuntimeSettings(
    publication_enabled=True,
    publication_delay_min_seconds=15,
    publication_delay_max_seconds=30,
    publication_interval_min_minutes=60,
    publication_interval_max_minutes=90,
    telegram_folder_name="Реклама",
    promo_bot_username="@example_bot",
)


class RemoteSettingsTests(unittest.TestCase):
    def test_false_disables_publication(self) -> None:
        values = parse_remote_config_text(
            "#promo-publisher-config\nPUBLICATION_ENABLED=false",
            marker="promo-publisher-config",
        )
        settings = apply_remote_overrides(DEFAULTS, values)
        self.assertFalse(settings.publication_enabled)

    def test_runtime_values_are_overridden(self) -> None:
        values = parse_remote_config_text(
            "\n".join(
                [
                    "#promo-publisher-config",
                    "PUBLICATION_DELAY_MIN_SECONDS=40",
                    "PUBLICATION_DELAY_MAX_SECONDS=70",
                    "PUBLICATION_INTERVAL_MIN_MINUTES=120",
                    "PUBLICATION_INTERVAL_MAX_MINUTES=150",
                ]
            ),
            marker="promo-publisher-config",
        )
        settings = apply_remote_overrides(DEFAULTS, values)
        self.assertEqual(settings.publication_delay_min_seconds, 40)
        self.assertEqual(settings.publication_delay_max_seconds, 70)
        self.assertEqual(settings.publication_interval_min_minutes, 120)
        self.assertEqual(settings.publication_interval_max_minutes, 150)

    def test_secret_keys_are_rejected(self) -> None:
        with self.assertRaises(RemoteConfigError):
            parse_remote_config_text(
                "#promo-publisher-config\nTELEGRAM_API_HASH=secret",
                marker="promo-publisher-config",
            )

    def test_unknown_keys_are_rejected(self) -> None:
        with self.assertRaises(RemoteConfigError):
            parse_remote_config_text(
                "#promo-publisher-config\nUNKNOWN_SETTING=1",
                marker="promo-publisher-config",
            )


if __name__ == "__main__":
    unittest.main()
