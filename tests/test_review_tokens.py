import unittest
import os
import logging
import asyncio

os.environ.setdefault("SHEET_ID", "test-sheet")
os.environ.setdefault("GOOGLE_CREDENTIALS", "{\"type\":\"service_account\"}")
logging.getLogger().setLevel(logging.CRITICAL + 1)

import handlers
import keyboards


class ReviewTokenTests(unittest.TestCase):
    def test_finalize_review_cards_edits_all_refs(self):
        class FakeBot:
            def __init__(self):
                self.calls = []

            async def edit_message_text(self, **kwargs):
                self.calls.append(kwargs)

        class FakeContext:
            def __init__(self):
                self.bot = FakeBot()

        async def run_case():
            token = "deadbeef"
            await handlers.register_review_message(token, 101, 11)
            await handlers.register_review_message(token, 202, 22)
            context = FakeContext()
            await handlers._finalize_review_cards(context, token, "approve", "D25317414", "Zii", 101, 11)
            return context.bot.calls

        calls = asyncio.run(run_case())
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["chat_id"], 101)
        self.assertEqual(calls[0]["message_id"], 11)
        self.assertIn("✅ Approved", calls[0]["text"])
        self.assertIsNone(calls[0]["reply_markup"])
        self.assertEqual(calls[1]["chat_id"], 202)
        self.assertEqual(calls[1]["message_id"], 22)
        self.assertIn("✅ Already Approved", calls[1]["text"])

    def test_token_is_stable_for_same_submission(self):
        row = [
            "2026-08-19 15:18:00",
            "student@example.com",
            "Muhammad Khairulnizam Bin Ab Razak",
            "D25317414",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "https://drive.google.com/open?id=receipt-a",
            "Pending",
        ]

        self.assertEqual(handlers.build_review_token(row), handlers.build_review_token(list(row)))

    def test_token_changes_for_new_submission_same_matric(self):
        base_row = [
            "2026-08-19 15:18:00",
            "student@example.com",
            "Muhammad Khairulnizam Bin Ab Razak",
            "D25317414",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "https://drive.google.com/open?id=receipt-a",
            "Pending",
        ]
        newer_row = list(base_row)
        newer_row[0] = "2026-08-19 15:58:00"
        newer_row[16] = "https://drive.google.com/open?id=receipt-b"

        self.assertNotEqual(handlers.build_review_token(base_row), handlers.build_review_token(newer_row))

    def test_review_callback_payload_keeps_token(self):
        token = "deadbeef"
        markup = keyboards.get_admin_confirm_keyboard("approve", 12, "D25317414", token, "EN")
        callback_data = markup.inline_keyboard[0][0].callback_data

        parsed = handlers._parse_review_callback_data(callback_data, "review_do_approve")
        self.assertEqual(parsed, (12, "D25317414", token))


if __name__ == "__main__":
    unittest.main()
