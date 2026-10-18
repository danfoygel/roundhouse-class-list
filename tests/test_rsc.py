import unittest

from classlist import rsc


class ParseChunksTest(unittest.TestCase):
    def test_reads_json_and_text_chunks(self):
        # The text chunk is 5 bytes: "a", a newline, "b", and a 2-byte "é". No newline follows it.
        data = '0:["$@1",null]\n2:T5,a\nbé3:{"x":"$2"}\n'.encode("utf-8")
        chunks = rsc.parse_chunks(data)
        self.assertEqual(chunks["0"], ("J", '["$@1",null]'))
        self.assertEqual(chunks["2"], ("T", "a\nbé"))
        self.assertEqual(chunks["3"], ("J", '{"x":"$2"}'))

    def test_skips_lines_that_are_not_chunks(self):
        chunks = rsc.parse_chunks(b'\nnot a chunk\n5:{"a":1}\n')
        self.assertEqual(list(chunks), ["5"])


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.chunks = rsc.parse_chunks(b'2:T3,abc\n3:{"id":"s1","label":"$2"}\n')

    def test_replaces_references_everywhere(self):
        value = {"description": "$2", "staff": ["$3", {"nested": "$2"}]}
        self.assertEqual(
            rsc.resolve(value, self.chunks),
            {"description": "abc", "staff": [{"id": "s1", "label": "abc"}, {"nested": "abc"}]},
        )

    def test_leaves_names_and_unknown_references_alone(self):
        value = {"name": "$2", "other": "$ff", "price": "$65"}
        self.assertEqual(rsc.resolve(value, self.chunks), value)


class JsonAfterTest(unittest.TestCase):
    def test_finds_array_despite_brackets_inside_strings(self):
        text = 'xx"sessionTypes":[{"a":"]"},{"b":[1,2]}] trailing "x":[9]'
        self.assertEqual(rsc.json_after(text, '"sessionTypes":'), [{"a": "]"}, {"b": [1, 2]}])

    def test_missing_marker_returns_none(self):
        self.assertIsNone(rsc.json_after("nothing here", '"sessionTypes":'))


if __name__ == "__main__":
    unittest.main()
