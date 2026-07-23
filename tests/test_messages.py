import json
import tempfile
import unittest
from pathlib import Path

from app.messages import (
    choose_message,
    load_message_state,
    load_messages,
    save_sent_message,
)


class MessageRotationTests(unittest.TestCase):
    def test_repository_contains_100_unique_messages(self) -> None:
        messages = load_messages()
        self.assertEqual(len(messages), 100)
        self.assertEqual(len({message.id for message in messages}), 100)
        self.assertEqual(len({message.text for message in messages}), 100)

    def test_all_messages_are_used_before_pool_repeats(self) -> None:
        messages = load_messages()

        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "message_state.json"
            selected_ids: list[str] = []

            for _ in range(len(messages)):
                selected = choose_message(
                    messages=messages,
                    target=-1001234567890,
                    state_path=state_path,
                )
                selected_ids.append(selected.id)
                save_sent_message(
                    target=-1001234567890,
                    message_id=selected.id,
                    state_path=state_path,
                )

            self.assertEqual(len(set(selected_ids)), len(messages))

            next_message = choose_message(
                messages=messages,
                target=-1001234567890,
                state_path=state_path,
            )
            self.assertNotEqual(next_message.id, selected_ids[-1])

    def test_rotation_is_independent_for_each_target(self) -> None:
        messages = load_messages()

        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "message_state.json"
            selected = choose_message(
                messages=messages,
                target=1,
                state_path=state_path,
            )
            save_sent_message(1, selected.id, state_path)

            first_target_state = load_message_state(state_path)
            self.assertEqual(first_target_state["1"], [selected.id])
            self.assertNotIn("2", first_target_state)

    def test_old_string_state_format_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            state_path = Path(temporary_directory) / "message_state.json"
            state_path.write_text(
                json.dumps({"123": "promo_01"}),
                encoding="utf-8",
            )

            state = load_message_state(state_path)
            self.assertEqual(state, {"123": ["promo_01"]})


if __name__ == "__main__":
    unittest.main()
