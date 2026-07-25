from __future__ import annotations

import unittest

from omni_tts_core.ui_presenters import model_groups


class _Spec:
    def __init__(self, model_id: str, provider: str, display_name: str) -> None:
        self.model_id = model_id
        self.provider = provider
        self.display_name = display_name
        self.catalog_info: dict = {}


_SPECS = [
    _Spec("piper_a", "piper", "Piper A"),
    _Spec("vieneu_a", "vieneu", "VieNeu A"),
    _Spec("piper_b", "piper", "Piper B"),
    _Spec("omni_a", "omnivoice", "Omni A"),
    _Spec("mystery_a", "unknown_provider", "Mystery A"),
]


class GroupModelsTest(unittest.TestCase):
    def test_groups_follow_provider_registry_order(self) -> None:
        groups = model_groups.group_models_by_provider(_SPECS)
        ids = [group.provider_id for group in groups]
        self.assertEqual(ids[:3], ["omnivoice", "vieneu", "piper"])
        self.assertEqual(ids[-1], "unknown_provider")  # unknown providers appended

    def test_group_counts_and_labels(self) -> None:
        groups = {g.provider_id: g for g in model_groups.group_models_by_provider(_SPECS)}
        self.assertEqual(groups["piper"].count, 2)
        self.assertEqual(groups["piper"].label, "Piper ONNX")
        self.assertEqual(groups["unknown_provider"].label, "unknown_provider")

    def test_provider_choices_include_all_with_total(self) -> None:
        choices = model_groups.provider_choices(_SPECS)
        self.assertEqual(choices[0][1], model_groups.ALL_PROVIDERS)
        self.assertIn("(5)", choices[0][0])
        self.assertIn(("Piper ONNX (2)", "piper"), choices)

    def test_models_for_provider_filters(self) -> None:
        piper = model_groups.models_for_provider(_SPECS, "piper")
        self.assertEqual([mid for _label, mid in piper], ["piper_a", "piper_b"])
        everything = model_groups.models_for_provider(_SPECS, model_groups.ALL_PROVIDERS)
        self.assertEqual(len(everything), 5)
        self.assertEqual(model_groups.models_for_provider(_SPECS, "nope"), [])

    def test_provider_choices_count_any_object_with_provider(self) -> None:
        """The model-management table passes ModelStatus, not ModelSpec."""

        class _Status:
            def __init__(self, provider: str) -> None:
                self.provider = provider
                self.display_name = "x"

        choices = model_groups.provider_choices([_Status("piper"), _Status("piper")])
        self.assertIn(("Piper ONNX (2)", "piper"), choices)
        self.assertEqual(choices[0], ("Tất cả (2)", model_groups.ALL_PROVIDERS))

    def test_filter_by_provider(self) -> None:
        kept = model_groups.filter_by_provider(_SPECS, "piper")
        self.assertEqual([s.model_id for s in kept], ["piper_a", "piper_b"])
        self.assertEqual(len(model_groups.filter_by_provider(_SPECS, model_groups.ALL_PROVIDERS)), 5)
        self.assertEqual(len(model_groups.filter_by_provider(_SPECS, None)), 5)

    def test_sort_by_provider_groups_rows_in_registry_order(self) -> None:
        ordered = model_groups.sort_by_provider(_SPECS)
        self.assertEqual(
            [s.provider for s in ordered],
            ["omnivoice", "vieneu", "piper", "piper", "unknown_provider"],
        )
        # within a provider, rows sort by display name
        piper = [s.display_name for s in ordered if s.provider == "piper"]
        self.assertEqual(piper, ["Piper A", "Piper B"])

    def test_provider_of_model(self) -> None:
        self.assertEqual(model_groups.provider_of_model(_SPECS, "vieneu_a"), "vieneu")
        self.assertEqual(model_groups.provider_of_model(_SPECS, "missing"), model_groups.ALL_PROVIDERS)
        self.assertEqual(model_groups.provider_of_model(_SPECS, None), model_groups.ALL_PROVIDERS)


if __name__ == "__main__":
    unittest.main()
