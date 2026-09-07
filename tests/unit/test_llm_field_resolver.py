import pytest
from unittest.mock import MagicMock
from backend.app.services.llm_field_resolver import LLMFieldResolver

def test_llm_resolver_disabled():
    resolver = LLMFieldResolver()
    resolver.enabled = False
    res = resolver.resolve("Some ATC text", ["payment_terms_supply_display"])
    assert res == {}

def test_llm_resolver_missing_fields_empty():
    resolver = LLMFieldResolver()
    res = resolver.resolve("Some ATC text", [])
    assert res == {}

def test_llm_resolver_unconfigured_api_key():
    with pytest.raises(RuntimeError):
        LLMFieldResolver(api_key="your_claude_api_key_placeholder")

def test_llm_resolver_role1_tool_use():
    resolver = LLMFieldResolver(api_key="sk-ant-test-key-12345")
    resolver.enabled = True
    
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_missing_fields"
    mock_block.input = {
        "payment_terms_supply_pct": 70,
        "payment_terms_installation_pct": 30,
        "ld_percentage_per_week": 0.5,
        "maf_required": True,
        "client_name_1": "RAMAR E",
        "client_email_1": "ramar@gail.co.in"
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.stop_reason = "end_turn"
    mock_response.usage.input_tokens = 120
    mock_response.usage.output_tokens = 45
    mock_response.usage.cache_creation_input_tokens = 0
    mock_response.usage.cache_read_input_tokens = 0
    resolver.client.messages.create = MagicMock(return_value=mock_response)
    
    atc_text = "GAIL payment terms: 70% of supply value and 30% installation. RAMAR E nodal officer email ramar@gail.co.in. PRS delay 0.5%. MAF Required."
    
    res = resolver.resolve(atc_text, [
        "payment_terms_supply_display",
        "payment_terms_installation_display",
        "ld_percentage_display",
        "maf_required_display",
        "client_name_1_display",
        "client_email_1_display"
    ])
    
    assert res["payment_terms_supply_display"]["value"] == "70%"
    assert res["payment_terms_installation_display"]["value"] == "30%"
    assert res["ld_percentage_display"]["value"] == "0.5%"
    assert res["maf_required_display"]["value"] == "Yes"
    assert res["client_name_1_display"]["value"] == "RAMAR E"
    assert res["client_email_1_display"]["value"] == "ramar@gail.co.in"
    # Category batching: 4 categories (payment_terms, prs_ld, bec_criteria, contacts_bds) -> 4 calls
    assert resolver.client.messages.create.call_count == 4
    assert resolver.total_input_tokens == 4 * 120
    assert resolver.total_output_tokens == 4 * 45
    assert resolver.total_raw_processing_tokens == (4 * 120) + (4 * 45)
    # Verify prompt caching and tight max_tokens on every category call
    for call in resolver.client.messages.create.call_args_list:
        kwargs = call[1]
        assert kwargs["max_tokens"] == 600
        assert kwargs["model"] == "claude-haiku-4-5-20251001"
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert kwargs["tools"][0]["cache_control"] == {"type": "ephemeral"}


def test_llm_resolver_role2_tool_use():
    resolver = LLMFieldResolver(api_key="sk-ant-test-key-12345")
    resolver.enabled = True

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "resolve_ambiguous_fields"
    mock_block.input = {
        "decisions": [
            {
                "field_name": "payment_terms_supply_display",
                "action": "confirm",
                "resolved_value": "70%",
                "reasoning": "Special Conditions Part-B explicitly specify 70% after receipt."
            },
            {
                "field_name": "net_worth_type_display",
                "action": "override",
                "resolved_value": "Not Applicable",
                "reasoning": "BEC unconditionally exempts all financial criteria."
            }
        ]
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 250
    mock_response.usage.output_tokens = 60
    resolver.client.messages.create = MagicMock(return_value=mock_response)

    candidates = {
        "payment_terms_supply_display": "70%",
        "net_worth_type_display": "Positive",
    }
    res = resolver.resolve_ambiguous_fields("Document full text...", candidates)
    assert res["payment_terms_supply_display"]["action"] == "confirm"
    assert res["payment_terms_supply_display"]["resolved_value"] == "70%"
    assert res["net_worth_type_display"]["action"] == "override"
    assert res["net_worth_type_display"]["resolved_value"] == "Not Applicable"


def test_llm_resolver_role2_delivery_time_descriptive_fallback():
    resolver = LLMFieldResolver(api_key="sk-ant-test-key-12345")
    resolver.enabled = True

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "resolve_ambiguous_fields"
    mock_block.input = {
        "decisions": [
            {
                "field_name": "delivery_time_supply_display",
                "action": "confirm",
                "resolved_value": "Not Specified",
                "reasoning": "No distinct supply schedule found."
            }
        ]
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 200
    mock_response.usage.output_tokens = 40
    resolver.client.messages.create = MagicMock(return_value=mock_response)

    candidates = {
        "delivery_time_supply_display": "90 Days",
    }
    res = resolver.resolve_ambiguous_fields("ATC text without supply period...", candidates)
    val = res["delivery_time_supply_display"]["resolved_value"]
    assert "90 Days" in val
    assert "total completion" in val
    assert "no distinct supply-only figure found" in val


def test_record_correction_updates_memory(tmp_path, monkeypatch):
    from backend.app.services.llm_field_resolver import record_correction, _load_memory, _MEMORY_FILE
    
    test_mem = tmp_path / "test_memory.json"
    monkeypatch.setattr("backend.app.services.llm_field_resolver._MEMORY_FILE", test_mem)
    monkeypatch.setattr("backend.app.services.llm_field_resolver._MEMORY_DIR", tmp_path)
    
    # 1. First correction
    record_correction("payment_terms_supply_display", "70%", "Payment terms 70% supply receipt")
    mem1 = _load_memory()
    assert len(mem1.get("payment_terms_supply_display", [])) == 1
    assert mem1["payment_terms_supply_display"][0]["value"] == "70%"
    
    # 2. Updated correction for same anchor should replace, not duplicate
    record_correction("payment_terms_supply_display", "80%", "Payment terms 70% supply receipt")
    mem2 = _load_memory()
    assert len(mem2.get("payment_terms_supply_display", [])) == 1
    assert mem2["payment_terms_supply_display"][0]["value"] == "80%"
    assert mem2["payment_terms_supply_display"][0]["confidence"] == 0.99


def test_reasoning_source_tagging_invariant():
    """
    ISSUE 2 TEST: Verify that any field with a non-null reasoning field
    is always tagged with source in ('llm', 'llm_override') — never 'regex' or 'atc'.
    """
    import sys
    from pathlib import Path
    tms_dir = Path(__file__).resolve().parent.parent.parent.parent / "TMS" / "tms" / "volksAi"
    if str(tms_dir) not in sys.path:
        sys.path.insert(0, str(tms_dir))
    from app.routers.extract import _format_field_object

    # Case 1: Role 2 confirmed a field that originally came from ATC
    res_confirmed = _format_field_object(
        field_name="payment_terms_supply_display",
        raw_val="80%",
        field_statuses={"payment_terms_supply_display": "ok"},
        field_sources={"payment_terms_supply_display": "atc"},
        reasoning="Tender explicitly states 80% under Section 3.1(a)"
    )
    assert res_confirmed["reasoning"] == "Tender explicitly states 80% under Section 3.1(a)"
    assert res_confirmed["source"] in ("llm", "llm_override")
    assert res_confirmed["source"] not in ("atc", "regex")

    # Case 2: Role 2 overrode a field that originally came from regex
    res_overridden = _format_field_object(
        field_name="net_worth_type_display",
        raw_val="Not Applicable",
        field_statuses={"net_worth_type_display": "ok_fallback"},
        field_sources={"net_worth_type_display": "regex"},
        reasoning="Overridden: Section-II BEC unconditionally exempts financial criteria"
    )
    assert res_overridden["reasoning"] is not None
    assert res_overridden["source"] in ("llm", "llm_override")
    assert res_overridden["source"] not in ("atc", "regex")

    # Case 3: Pure ATC extraction without LLM reasoning must remain 'atc'
    res_pure_atc = _format_field_object(
        field_name="pbg_percentage_display",
        raw_val="5.0%",
        field_statuses={"pbg_percentage_display": "ok"},
        field_sources={"pbg_percentage_display": "atc"},
        reasoning=None
    )
    assert "reasoning" not in res_pure_atc
    assert res_pure_atc["source"] == "atc"

    # Case 4: Pure Regex extraction without LLM reasoning must remain 'regex'
    res_pure_regex = _format_field_object(
        field_name="bid_validity_days_display",
        raw_val="90 Days",
        field_statuses={"bid_validity_days_display": "ok"},
        field_sources={"bid_validity_days_display": "main_tender"},
        reasoning=None
    )
    assert "reasoning" not in res_pure_regex
    assert res_pure_regex["source"] == "regex"


def test_role1_truncation_retry():
    """
    Test Change 4/reliability requirement:
    When Role 1 encounters stop_reason == 'max_tokens', it immediately retries once
    with max_tokens=1000 and increments self.role1_retries.
    """
    resolver = LLMFieldResolver(api_key="sk-ant-test-key-12345")
    resolver.enabled = True

    # 1st call: truncated at max_tokens
    mock_resp_1 = MagicMock()
    mock_resp_1.stop_reason = "max_tokens"
    mock_resp_1.content = []
    mock_resp_1.usage.input_tokens = 500
    mock_resp_1.usage.output_tokens = 600
    mock_resp_1.usage.cache_creation_input_tokens = 0
    mock_resp_1.usage.cache_read_input_tokens = 0

    # 2nd call: retry succeeds
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_missing_fields"
    mock_block.input = {"payment_terms_supply_pct": 80}

    mock_resp_2 = MagicMock()
    mock_resp_2.stop_reason = "end_turn"
    mock_resp_2.content = [mock_block]
    mock_resp_2.usage.input_tokens = 500
    mock_resp_2.usage.output_tokens = 60
    mock_resp_2.usage.cache_creation_input_tokens = 0
    mock_resp_2.usage.cache_read_input_tokens = 0

    resolver.client.messages.create = MagicMock(side_effect=[mock_resp_1, mock_resp_2])

    atc_text = "GAIL payment terms: 80% on supply of materials."
    res = resolver.resolve(atc_text, ["payment_terms_supply_display"])

    assert resolver.role1_retries == 1
    assert resolver.client.messages.create.call_count == 2
    # Verify first call used 600 tokens and retry call used 1000 tokens
    first_call_max = resolver.client.messages.create.call_args_list[0][1]["max_tokens"]
    retry_call_max = resolver.client.messages.create.call_args_list[1][1]["max_tokens"]
    assert first_call_max == 600
    assert retry_call_max == 1000
    assert res["payment_terms_supply_display"]["value"] == "80%"


def test_verified_pricing_and_usage_summary():
    """
    Test Change 2 verified pricing constants and multi-metric integer tracking.
    Haiku 4.5: $1.00 / MTok in, $5.00 / MTok out, $1.25 cache write, $0.10 cache read.
    Sonnet 5: $2.00 / MTok in, $10.00 / MTok out, $2.50 cache write, $0.20 cache read.
    """
    from backend.app.services.llm_field_resolver import (
        HAIKU_45_INPUT_PRICE_PER_M,
        HAIKU_45_OUTPUT_PRICE_PER_M,
        HAIKU_45_CACHE_WRITE_5M_PER_M,
        HAIKU_45_CACHE_READ_PER_M,
        SONNET_5_INPUT_PRICE_PER_M,
        SONNET_5_OUTPUT_PRICE_PER_M,
        SONNET_5_CACHE_WRITE_5M_PER_M,
        SONNET_5_CACHE_READ_PER_M,
        LLM_TOKEN_BUDGET_PER_TENDER,
    )

    # Verify official constants
    assert HAIKU_45_INPUT_PRICE_PER_M == 1.00
    assert HAIKU_45_OUTPUT_PRICE_PER_M == 5.00
    assert HAIKU_45_CACHE_WRITE_5M_PER_M == 1.25
    assert HAIKU_45_CACHE_READ_PER_M == 0.10

    assert SONNET_5_INPUT_PRICE_PER_M == 2.00
    assert SONNET_5_OUTPUT_PRICE_PER_M == 10.00
    assert SONNET_5_CACHE_WRITE_5M_PER_M == 2.50
    assert SONNET_5_CACHE_READ_PER_M == 0.20

    assert LLM_TOKEN_BUDGET_PER_TENDER == 20000

    resolver = LLMFieldResolver(api_key="sk-ant-test-key-12345")
    
    # 1. Haiku 4.5 usage (Role 1)
    mock_haiku_usage = MagicMock()
    mock_haiku_usage.input_tokens = 1_000_000
    mock_haiku_usage.output_tokens = 100_000
    mock_haiku_usage.cache_creation_input_tokens = 500_000
    mock_haiku_usage.cache_read_input_tokens = 200_000
    resolver.record_usage(mock_haiku_usage, role="role1")

    # Expected Haiku cost:
    # 1.00 * 1.0 = 1.00 (in)
    # 0.10 * 5.0 = 0.50 (out)
    # 0.50 * 1.25 = 0.625 (cache write)
    # 0.20 * 0.10 = 0.02 (cache read)
    # Total = 2.145 USD
    assert abs(resolver.total_cost_usd - 2.145) < 1e-4

    # 2. Sonnet 5 usage (Role 2)
    mock_sonnet_usage = MagicMock()
    mock_sonnet_usage.input_tokens = 500_000
    mock_sonnet_usage.output_tokens = 50_000
    mock_sonnet_usage.cache_creation_input_tokens = 200_000
    mock_sonnet_usage.cache_read_input_tokens = 100_000
    resolver.record_usage(mock_sonnet_usage, role="role2")

    # Expected Sonnet addition:
    # 0.50 * 2.0 = 1.00 (in)
    # 0.05 * 10.0 = 0.50 (out)
    # 0.20 * 2.50 = 0.50 (cache write)
    # 0.10 * 0.20 = 0.02 (cache read)
    # Total addition = 2.02 USD -> cumulative 4.165 USD
    assert abs(resolver.total_cost_usd - 4.165) < 1e-4

    # Gated raw processing tokens must be exact integer sum
    expected_raw_tokens = (
        (1_000_000 + 100_000 + 500_000 + 200_000)
        + (500_000 + 50_000 + 200_000 + 100_000)
    )
    assert resolver.total_raw_processing_tokens == expected_raw_tokens

    summary = resolver.get_usage_summary()
    assert summary["role1_model"] == "claude-haiku-4-5-20251001"
    assert summary["role2_model"] == "claude-sonnet-5"
    assert summary["raw_tokens"] == expected_raw_tokens
    assert summary["estimated_cost_usd"] == 4.165


def test_role2_prompt_caching_and_tight_tokens():
    """
    Test Change 3 and Change 4 for Role 2:
    ROLE_2_MAX_TOKENS = 800, model claude-sonnet-5, and ephemeral prompt caching.
    """
    from backend.app.services.llm_field_resolver import ROLE_2_MAX_TOKENS
    assert ROLE_2_MAX_TOKENS == 800

    resolver = LLMFieldResolver(api_key="sk-ant-test-key-12345")
    resolver.enabled = True

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "resolve_ambiguous_fields"
    mock_block.input = {
        "decisions": [
            {
                "field_name": "net_worth_type_display",
                "action": "confirm",
                "resolved_value": "Not Applicable",
                "reasoning": "BEC unconditionally exempts Net Worth."
            }
        ]
    }
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 150
    mock_response.usage.output_tokens = 40
    mock_response.usage.cache_creation_input_tokens = 0
    mock_response.usage.cache_read_input_tokens = 0
    resolver.client.messages.create = MagicMock(return_value=mock_response)

    res = resolver.resolve_ambiguous_fields(
        "Tender clauses...",
        {"net_worth_type_display": "Not Applicable"}
    )
    assert res["net_worth_type_display"]["action"] == "confirm"

    call_kwargs = resolver.client.messages.create.call_args[1]
    assert call_kwargs["max_tokens"] == 800
    assert call_kwargs["model"] == "claude-sonnet-5"
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call_kwargs["tools"][0]["cache_control"] == {"type": "ephemeral"}


def test_is_unambiguous_layer1_logic():
    """
    Test Change 6: is_unambiguous_layer1 correctly detects unambiguous vs conflicting candidates.
    """
    from backend.app.services.llm_field_resolver import is_unambiguous_layer1

    # Net Worth: unambiguous when only one clear condition exists
    text_unambig_nw = "Section-II BEC: Financial Criteria: Not Applicable for this tender."
    assert is_unambiguous_layer1("net_worth_type_display", "Not Applicable", text_unambig_nw) is True

    # Net Worth: ambiguous when GCC boilerplate says 'must be positive' while BEC says 'not applicable'
    text_ambig_nw = (
        "GCC Clause 2.1: The Net Worth of the Bidder must be positive.\n"
        "BEC Section-II: Financial Criteria is Not Applicable for all bidders."
    )
    assert is_unambiguous_layer1("net_worth_type_display", "Positive", text_ambig_nw) is False

    # Delivery time: unambiguous when single delivery period mentioned
    text_unambig_del = "Delivery Schedule: Delivery period is 90 Days from the date of FOA."
    assert is_unambiguous_layer1("delivery_time_supply_display", "90 Days", text_unambig_del) is True

    # Delivery time: ambiguous when both 90 days and 150 days appear in delivery clauses
    text_ambig_del = (
        "Delivery Schedule: Goods supply delivery period is 90 Days.\n"
        "Overall completion schedule: Total completion period is 150 Days."
    )
    assert is_unambiguous_layer1("delivery_time_supply_display", "90 Days", text_ambig_del) is False


def test_pre_role2_budget_checkpoint_logic():
    """
    Test Change 5: When remaining budget < 4000 raw tokens,
    Priority 1 (net_worth_type_display) is kept while Priority 2/3 are deferred with 'skipped_budget_exhaustion'.
    """
    from backend.app.services.llm_field_resolver import (
        AMBIGUITY_FIELD_PRIORITY,
        LLM_TOKEN_BUDGET_PER_TENDER,
    )

    candidates = {
        "net_worth_type_display": "Positive",
        "payment_terms_supply_display": "70%",
        "delivery_time_supply_display": "90 Days",
    }

    # Simulate Role 1 consuming 17,000 tokens (remaining budget = 3,000 < 4,000)
    current_raw_tokens = 17000
    remaining_budget = LLM_TOKEN_BUDGET_PER_TENDER - current_raw_tokens
    assert remaining_budget < 4000

    ambig_dispositions = {}
    eligible_candidates = {}

    for f_name, c_val in candidates.items():
        f_prio = AMBIGUITY_FIELD_PRIORITY.get(f_name, 3)
        if remaining_budget < 4000 and f_prio > 1:
            ambig_dispositions[f_name] = "skipped_budget_exhaustion"
        else:
            ambig_dispositions[f_name] = "evaluated_role2"
            eligible_candidates[f_name] = c_val

    # Priority 1 was kept
    assert ambig_dispositions["net_worth_type_display"] == "evaluated_role2"
    assert "net_worth_type_display" in eligible_candidates

    # Priority 2 and 3 were deferred with explicit disposition
    assert ambig_dispositions["payment_terms_supply_display"] == "skipped_budget_exhaustion"
    assert ambig_dispositions["delivery_time_supply_display"] == "skipped_budget_exhaustion"
    assert "payment_terms_supply_display" not in eligible_candidates
    assert "delivery_time_supply_display" not in eligible_candidates



