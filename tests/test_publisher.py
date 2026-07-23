import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


try:
    import telethon  # noqa: F401
except ModuleNotFoundError:
    telethon_module = types.ModuleType("telethon")
    errors_module = types.ModuleType("telethon.errors")
    utils_module = types.ModuleType("telethon.utils")
    tl_module = types.ModuleType("telethon.tl")
    functions_module = types.ModuleType("telethon.tl.functions")
    messages_module = types.ModuleType("telethon.tl.functions.messages")
    types_module = types.ModuleType("telethon.tl.types")

    class TelegramClient:
        pass

    class RPCError(Exception):
        pass

    class SlowModeWaitError(RPCError):
        seconds = 1

    class FloodWaitError(RPCError):
        seconds = 1

    class GetDialogFiltersRequest:
        pass

    class Channel:
        pass

    class Chat:
        pass

    class User:
        pass

    errors_module.RPCError = RPCError
    errors_module.SlowModeWaitError = SlowModeWaitError
    errors_module.FloodWaitError = FloodWaitError
    utils_module.get_display_name = lambda entity: str(entity)
    utils_module.get_peer_id = lambda entity: 0
    messages_module.GetDialogFiltersRequest = GetDialogFiltersRequest
    types_module.Channel = Channel
    types_module.Chat = Chat
    types_module.User = User

    telethon_module.TelegramClient = TelegramClient
    telethon_module.errors = errors_module
    telethon_module.utils = utils_module

    sys.modules["telethon"] = telethon_module
    sys.modules["telethon.errors"] = errors_module
    sys.modules["telethon.utils"] = utils_module
    sys.modules["telethon.tl"] = tl_module
    sys.modules["telethon.tl.functions"] = functions_module
    sys.modules["telethon.tl.functions.messages"] = messages_module
    sys.modules["telethon.tl.types"] = types_module


from app.folder_targets import PublicationTarget
from app.messages import PromoMessage
from app.publisher import PlannedPublication, publish_plan
from app.settings import LoadedSettings, RemoteConfigError, RuntimeSettings


class FakeClient:
    def __init__(self) -> None:
        self.send_calls = 0

    async def send_message(self, **kwargs):
        self.send_calls += 1
        return type("SentMessage", (), {"id": 1})()


def make_settings(*, enabled: bool) -> LoadedSettings:
    return LoadedSettings(
        settings=RuntimeSettings(
            publication_enabled=enabled,
            publication_delay_min_seconds=0,
            publication_delay_max_seconds=0,
            publication_interval_min_minutes=60,
            publication_interval_max_minutes=90,
            publication_message_gate_enabled=False,
            publication_min_new_messages=10,
            telegram_folder_name="Реклама",
            promo_bot_username="@example_bot",
        ),
        source="test",
    )


def make_plan() -> list[PlannedPublication]:
    target = PublicationTarget(
        name="Тестовый чат",
        peer=object(),
        peer_id=-1001234567890,
        kind="supergroup",
    )
    message = PromoMessage(
        id="promo_test",
        text="Тест: {bot_username}",
    )
    return [
        PlannedPublication(
            target=target,
            message=message,
            rendered_text=message.render("@example_bot"),
        )
    ]


class PublicationKillSwitchTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.publisher.append_history")
    async def test_disabled_config_prevents_send(self, _append_history) -> None:
        client = FakeClient()

        async def settings_loader() -> LoadedSettings:
            return make_settings(enabled=False)

        summary = await publish_plan(
            client=client,
            plan=make_plan(),
            settings_loader=settings_loader,
            config_check_seconds=1,
        )

        self.assertEqual(client.send_calls, 0)
        self.assertTrue(summary.disabled_by_config)
        self.assertEqual(summary.successful, 0)


    @patch("app.publisher.append_history")
    @patch("app.publisher.check_message_gate", new_callable=AsyncMock)
    async def test_message_gate_prevents_send(
        self,
        gate_mock: AsyncMock,
        _append_history,
    ) -> None:
        from app.message_gate import MessageGateStatus

        client = FakeClient()
        loaded = make_settings(enabled=True)
        loaded = LoadedSettings(
            settings=RuntimeSettings(
                **{
                    **loaded.settings.__dict__,
                    "publication_message_gate_enabled": True,
                    "publication_min_new_messages": 10,
                }
            ),
            source="test",
        )
        gate_mock.return_value = MessageGateStatus(
            allowed=False,
            new_message_count=4,
            required_message_count=10,
            last_sent_message_id=123,
        )

        async def settings_loader() -> LoadedSettings:
            return loaded

        summary = await publish_plan(
            client=client,
            plan=make_plan(),
            settings_loader=settings_loader,
            config_check_seconds=1,
        )

        self.assertEqual(client.send_calls, 0)
        self.assertEqual(summary.skipped_by_message_gate, 1)
        self.assertEqual(summary.successful, 0)

    async def test_invalid_remote_config_prevents_send(self) -> None:
        client = FakeClient()

        async def settings_loader() -> LoadedSettings:
            raise RemoteConfigError("Некорректный конфиг")

        summary = await publish_plan(
            client=client,
            plan=make_plan(),
            settings_loader=settings_loader,
            config_check_seconds=1,
        )

        self.assertEqual(client.send_calls, 0)
        self.assertEqual(summary.successful, 0)
        self.assertIsNotNone(summary.aborted_reason)


if __name__ == "__main__":
    unittest.main()
