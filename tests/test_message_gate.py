import json
import tempfile
import unittest
from pathlib import Path

from app.message_gate import (
    count_new_external_messages,
    get_last_sent_message_id,
    save_last_sent_message_id,
)


class FakeMessage:
    def __init__(
        self,
        message_id: int,
        *,
        out: bool = False,
        action: object | None = None,
    ) -> None:
        self.id = message_id
        self.out = out
        self.action = action


class FakeClient:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages

    async def iter_messages(self, **_kwargs):
        for message in self.messages:
            yield message


class MessageGateStateTests(unittest.TestCase):
    def test_restores_last_message_id_from_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history_path = root / "publication_history.jsonl"
            state_path = root / "message_gate_state.json"
            records = [
                {
                    "target_id": -1001,
                    "status": "sent",
                    "telegram_message_id": 25,
                },
                {
                    "target_id": -1001,
                    "status": "waiting_for_new_messages",
                    "telegram_message_id": None,
                },
                {
                    "target_id": -1001,
                    "status": "sent",
                    "telegram_message_id": 40,
                },
            ]
            history_path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )

            result = get_last_sent_message_id(
                target_id=-1001,
                state_path=state_path,
                history_path=history_path,
            )

            self.assertEqual(result, 40)

    def test_saved_state_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "message_gate_state.json"
            history_path = root / "publication_history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "target_id": -1001,
                        "status": "sent",
                        "telegram_message_id": 40,
                    }
                ),
                encoding="utf-8",
            )
            save_last_sent_message_id(
                target_id=-1001,
                telegram_message_id=55,
                state_path=state_path,
            )

            result = get_last_sent_message_id(
                target_id=-1001,
                state_path=state_path,
                history_path=history_path,
            )

            self.assertEqual(result, 55)


class MessageGateCountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_counts_only_external_non_service_messages(self) -> None:
        client = FakeClient(
            [
                FakeMessage(101),
                FakeMessage(102, out=True),
                FakeMessage(103, action=object()),
                FakeMessage(104),
                FakeMessage(105),
            ]
        )

        count = await count_new_external_messages(
            client=client,
            entity=object(),
            after_message_id=100,
            stop_after=3,
        )

        self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
