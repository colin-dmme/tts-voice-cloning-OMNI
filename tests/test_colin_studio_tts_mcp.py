from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from colin_studio_tts_mcp.contracts import (
    FileGenerationInput,
    OutputOptions,
    TextGenerationInput,
    VoiceSelection,
)
from colin_studio_tts_mcp.job_manager import public_job
from colin_studio_tts_mcp.job_store import McpJobStore


class McpContractTests(unittest.TestCase):
    def test_maps_nested_contract_to_core_settings(self) -> None:
        request = TextGenerationInput(
            text="Xin chào",
            model_id="omnivoice_vietnamese",
            voice=VoiceSelection(mode="design", voice_id="design-1"),
            output=OutputOptions(mode="merged", audio_format="mp3", create_srt=True),
            generation={
                "speed": 1.1,
                "provider_options": {"quality": 8},
                "advanced": {"sentence_pause_ms": 410},
            },
        )

        settings = request.to_settings()
        core_request = settings.to_request(request.text)

        self.assertEqual(core_request.voice_source_mode, "design")
        self.assertEqual(core_request.designed_voice_id, "design-1")
        self.assertEqual(core_request.output_mode, "merged")
        self.assertEqual(core_request.output_audio_format, "mp3")
        self.assertEqual(core_request.sentence_pause_ms, 410)
        self.assertFalse(core_request.overwrite)

    def test_rejects_unknown_advanced_setting(self) -> None:
        request = TextGenerationInput(
            text="Xin chào",
            model_id="omnivoice_vietnamese",
            generation={"advanced": {"gui_checkbox_state": True}},
        )
        with self.assertRaisesRegex(ValueError, "không hỗ trợ"):
            request.to_settings()

    def test_rejects_relative_source_path(self) -> None:
        with self.assertRaises(ValidationError):
            FileGenerationInput(
                source_files=["relative.txt"],
                model_id="omnivoice_vietnamese",
            )

    def test_accepts_supported_absolute_source_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.md"
            source.write_text("Nội dung", encoding="utf-8")
            request = FileGenerationInput(
                source_files=[str(source), str(source)],
                model_id="omnivoice_vietnamese",
            )
            self.assertEqual(request.source_files, [str(source.resolve())])


class McpJobStoreTests(unittest.TestCase):
    def test_persists_job_and_public_view_omits_full_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = McpJobStore(Path(directory) / "jobs.sqlite3")
            record = store.create(
                "text",
                {
                    "text": "Một nội dung rất dài",
                    "model_id": "model-a",
                    "voice": {"mode": "fixed", "voice_id": "speaker-a"},
                    "output": {},
                },
            )
            updated = store.update(
                record["job_id"],
                status="succeeded",
                progress=100.0,
                message="Hoàn tất",
                result_json='{"audio_path": "C:/out.wav"}',
            )
            public = public_job(updated)

            self.assertEqual(public["status"], "succeeded")
            self.assertEqual(public["result"]["audio_path"], "C:/out.wav")
            self.assertNotIn("request", public)
            self.assertEqual(public["request_summary"]["text_length"], 20)


try:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    from colin_studio_tts_mcp.server import mcp
except ImportError:  # The MCP dependency is an optional project extra.
    Client = None
    StdioServerParameters = None
    stdio_client = None
    mcp = None


@unittest.skipIf(Client is None, "Install the mcp project extra")
class McpProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_discoverable_and_health_is_callable(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            self.assertEqual(
                names,
                {
                    "health",
                    "list_models",
                    "get_generation_contract",
                    "list_voices",
                    "start_text_generation",
                    "start_file_generation",
                    "get_job",
                    "list_jobs",
                    "cancel_job",
                    "retry_job",
                },
            )
            result = await client.call_tool("health", {})
            self.assertEqual(result.structured_content["status"], "ok")
            self.assertEqual(
                result.structured_content["server"], "colin_studio_tts_mcp"
            )
            self.assertEqual(result.structured_content["version"], "0.5.1")
            models = await client.call_tool("list_models", {})
            self.assertGreater(models.structured_content["count"], 0)
            model_id = models.structured_content["models"][0]["model_id"]
            contract = await client.call_tool(
                "get_generation_contract", {"model_id": model_id}
            )
            self.assertEqual(contract.structured_content["model_id"], model_id)
            voices = await client.call_tool("list_voices", {"model_id": model_id})
            self.assertIn("voices", voices.structured_content)

            vieneu_contract = await client.call_tool(
                "get_generation_contract", {"model_id": "vieneu_v3_turbo"}
            )
            fixed = vieneu_contract.structured_content["fixed_voices"]
            self.assertEqual(len(fixed), 23)
            self.assertTrue(all(item["voice_id"] for item in fixed))
            self.assertEqual(
                vieneu_contract.structured_content["form"]["default_fixed_voice_id"],
                "Minh Quân",
            )
            self.assertIn("Adam", {item["voice_id"] for item in fixed})
            self.assertIn("Anh Khôi", {item["voice_id"] for item in fixed})

            vieneu_voices = await client.call_tool(
                "list_voices", {"model_id": "vieneu_v3_turbo"}
            )
            fixed_voices = [
                item
                for item in vieneu_voices.structured_content["voices"]
                if item["mode"] == "fixed"
            ]
            self.assertEqual(len(fixed_voices), 23)
            self.assertTrue(all(item["voice_id"] for item in fixed_voices))

            zerotts_contract = await client.call_tool(
                "get_generation_contract", {"model_id": "zerotts_202m_official"}
            )
            zero_data = zerotts_contract.structured_content
            self.assertEqual(zero_data["provider"], "zerotts")
            self.assertEqual(
                zero_data["form"]["default_fixed_voice_id"], "maichi"
            )
            self.assertIn(
                "audio_temperature",
                {item["key"] for item in zero_data["provider_settings"]},
            )
            zero_models = await client.call_tool(
                "list_models", {"provider_id": "zerotts"}
            )
            self.assertEqual(zero_models.structured_content["count"], 4)
            self.assertEqual(
                {
                    item["model_id"]
                    for item in zero_models.structured_content["models"]
                },
                {
                    "zerotts_202m_official",
                    "zerotts_202m_gguf_f32",
                    "zerotts_202m_gguf_q8_0",
                    "zerotts_202m_gguf_q4_0",
                },
            )
            gguf_contract = await client.call_tool(
                "get_generation_contract",
                {"model_id": "zerotts_202m_gguf_q8_0"},
            )
            gguf_keys = {
                item["key"]
                for item in gguf_contract.structured_content["provider_settings"]
            }
            self.assertEqual(len(gguf_keys), 20)
            self.assertNotIn("cfg_scale", gguf_keys)
            self.assertNotIn("warmup", gguf_keys)

    async def test_real_stdio_process_has_clean_protocol_output(self) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "colin_studio_tts_mcp.server"],
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        async with Client(stdio_client(params)) as client:
            result = await client.call_tool("health", {})
            self.assertEqual(result.structured_content["status"], "ok")


if __name__ == "__main__":
    unittest.main()
