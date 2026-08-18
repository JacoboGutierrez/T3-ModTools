import unittest
from string import Formatter


from t3_modtools import APP_VERSION, I18N, LANGUAGE_OPTIONS


class LocalizationTests(unittest.TestCase):
    def test_version_is_0_6_1_1(self):
        self.assertEqual("0.6.1.1", APP_VERSION)

    def test_language_selector_contains_all_supported_languages(self):
        self.assertEqual(
            (
                ("English", "en"),
                ("Español", "es"),
                ("Русский", "ru"),
                ("Português", "pt"),
            ),
            LANGUAGE_OPTIONS,
        )
        self.assertEqual({"en", "es", "ru", "pt"}, set(I18N))

    def test_every_language_has_a_complete_translation(self):
        english_keys = set(I18N["en"])
        for language, translations in I18N.items():
            with self.subTest(language=language):
                self.assertEqual(english_keys, set(translations))

    def test_translations_preserve_dynamic_placeholders(self):
        formatter = Formatter()

        def placeholders(text):
            return {
                field_name
                for _, field_name, _, _ in formatter.parse(text)
                if field_name is not None
            }

        for language, translations in I18N.items():
            for key, translation in translations.items():
                with self.subTest(language=language, key=key):
                    self.assertEqual(
                        placeholders(I18N["en"][key]),
                        placeholders(translation),
                    )


if __name__ == "__main__":
    unittest.main()
