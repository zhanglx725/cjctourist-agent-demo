"""CA-02 tests for metadata-only controlled tool registration."""

from __future__ import annotations

from dataclasses import replace
import unittest

from tool_registry import (
    DEFAULT_TOOL_SPECS,
    FailurePolicy,
    REGISTERED_TOOLS,
    RuntimePhase,
    SchemaSpec,
    ToolRegistryError,
    UnknownToolError,
    get_capability,
    get_tool,
    validate_registry,
)


class ToolRegistryTests(unittest.TestCase):
    EXPECTED_CAPABILITIES = {
        "single_fact", "visit_service", "controlled_knowledge", "term", "craft", "object",
        "point_inventory", "research", "comparison", "photo", "navigation",
    }

    def test_all_first_read_only_capabilities_are_registered(self):
        self.assertEqual({spec.capability for spec in REGISTERED_TOOLS}, self.EXPECTED_CAPABILITIES)
        self.assertEqual(len({spec.tool_name for spec in REGISTERED_TOOLS}), len(REGISTERED_TOOLS))
        self.assertEqual(len({spec.capability for spec in REGISTERED_TOOLS}), len(REGISTERED_TOOLS))
        for spec in REGISTERED_TOOLS:
            self.assertEqual(spec.side_effect_level.value, "read_only")
            self.assertFalse(spec.requires_confirmation)
            self.assertEqual(spec.max_calls_per_turn, 1)

    def test_each_registered_tool_has_complete_schema_state_and_failure_contract(self):
        for spec in REGISTERED_TOOLS:
            with self.subTest(tool=spec.tool_name):
                self.assertTrue(spec.input_schema.required_fields)
                self.assertTrue(spec.output_schema.required_fields)
                self.assertEqual(set(spec.allowed_phases), set(RuntimePhase))
                self.assertTrue(spec.evidence_requirements)
                self.assertGreater(spec.timeout_ms, 0)
                self.assertIn(spec.failure_policy, set(FailurePolicy))

    def test_unknown_tool_and_capability_are_rejected_by_default(self):
        with self.assertRaises(UnknownToolError):
            get_tool("arbitrary_code_execution")
        with self.assertRaises(UnknownToolError):
            get_capability("unregistered_capability")

    def test_duplicate_or_incomplete_registration_fails_closed(self):
        with self.assertRaisesRegex(ToolRegistryError, "duplicate_registration"):
            validate_registry((DEFAULT_TOOL_SPECS[0], DEFAULT_TOOL_SPECS[0]))
        incomplete = replace(DEFAULT_TOOL_SPECS[0], input_schema=SchemaSpec(()))
        with self.assertRaisesRegex(ToolRegistryError, "schema_incomplete"):
            validate_registry((incomplete,))

    def test_visitor_and_audit_fields_are_disjoint_and_internal_metadata_is_not_public(self):
        for spec in REGISTERED_TOOLS:
            with self.subTest(tool=spec.tool_name):
                self.assertFalse(set(spec.visitor_fields) & set(spec.audit_fields))
                self.assertNotIn("source_ids", spec.visitor_fields)
                self.assertIn("source_ids", spec.audit_fields)
                self.assertNotIn("evidence", spec.visitor_fields)

    def test_lookup_is_stable_and_registry_does_not_import_or_execute_backends(self):
        first = get_tool("reviewed_single_fact")
        second = get_capability("single_fact")
        self.assertEqual(first, second)
        self.assertEqual(first.tool_name, "reviewed_single_fact")


if __name__ == "__main__":
    unittest.main()
