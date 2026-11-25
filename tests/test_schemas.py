import math
import unittest
from runtime.schemas import SchemaError, validate, validate_request


class SchemaTests(unittest.TestCase):
    def test_request_unknown_fields_and_tools_rejected(self):
        request = {"tool": "draft.prepare", "client_id": "alpha", "arguments": {"text": "draft"}}
        self.assertEqual(validate_request(request), request)
        for change in ({"risk": "green"}, {"principal": "admin"}, {"approved": True}):
            with self.assertRaises(SchemaError):
                validate_request({**request, **change})
        for tool in ("shell", "email.send", "unknown"):
            with self.assertRaises(SchemaError):
                validate_request({**request, "tool": tool})

    def test_arguments_exact_types_and_bounds(self):
        for args in ({"text": "draft", "approved": True}, {"text": 4}, {}, {"text": "x" * 12001}):
            with self.assertRaises(SchemaError):
                validate_request({"tool": "draft.prepare", "client_id": "alpha", "arguments": args})
        for value in (True, math.nan, math.inf):
            with self.assertRaises(SchemaError):
                validate(value, {"type": "number"})

    def test_invalid_unicode_text_rejected(self):
        with self.assertRaises(SchemaError):
            validate_request({"tool": "draft.prepare", "client_id": "alpha", "arguments": {"text": "\ud800"}})

    def test_pathlike_client_ids_rejected(self):
        for client in ("../beta", "/beta", "alpha/beta", "alpha\\beta", "", "alpha\x00"):
            with self.assertRaises(SchemaError):
                validate_request({"tool": "overlay.read", "client_id": client,
                                  "arguments": {"document": "facts.json"}})


if __name__ == "__main__":
    unittest.main()
