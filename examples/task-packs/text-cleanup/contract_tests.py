import unittest

from solution import slugify


class SlugContract(unittest.TestCase):
    def test_accents(self):
        self.assertEqual(slugify("Café déjà vu!"), "cafe-deja-vu")

    def test_punctuation(self):
        self.assertEqual(slugify("  Hello___World / again  "), "hello-world-again")

    def test_digits(self):
        self.assertEqual(slugify("Release 2026.10"), "release-2026-10")

    def test_combining_mark(self):
        self.assertEqual(slugify("Cafe\u0301"), "cafe")

    def test_empty_or_no_ascii(self):
        for text in ("", " -- ", "中文", "🎯"):
            with self.subTest(text=text):
                self.assertEqual(slugify(text), "")
