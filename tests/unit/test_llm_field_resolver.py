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
    resolver = LLMFieldResolver()
    resolver.api_key = "LLM_API_KEY"  # placeholder key
    res = resolver.resolve("Some ATC text", ["payment_terms_supply_display"])
    extracted = {k: v for k, v in res.items() if k != "_llm_status"}
    assert extracted == {}

def test_llm_resolver_successful_parse():
    resolver = LLMFieldResolver()
    resolver.provider = "gemini"
    resolver._sdk_type = "genai_v2"
    resolver._init_gemini_client = MagicMock()
    resolver.api_key = "AIzaSyRealKeyStyleForTesting"
    resolver.enabled = True
    
    mock_json = """
    {
        "payment_terms_supply_pct": 70,
        "payment_terms_installation_pct": 30,
        "ld_percentage_per_week": 0.5,
        "maf_required": true,
        "client_name_1": "RAMAR E",
        "client_email_1": "ramar@gail.co.in"
    }
    """
    resolver._call_gemini_v2 = MagicMock(return_value=mock_json)
    resolver._call_openai_compatible = MagicMock(return_value=mock_json)
    
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

def test_llm_resolver_hallucination_filtering():
    resolver = LLMFieldResolver()
    resolver.provider = "gemini"
    resolver._sdk_type = "genai_v2"
    resolver._init_gemini_client = MagicMock()
    resolver.api_key = "AIzaSyRealKeyStyleForTesting"
    resolver.enabled = True
    
    mock_json = """
    {
        "client_name_1": "JOHN DOE",
        "client_name_2": "RAMAR E"
    }
    """
    resolver._call_gemini_v2 = MagicMock(return_value=mock_json)
    resolver._call_openai_compatible = MagicMock(return_value=mock_json)
    
    atc_text = "Tender officer is RAMAR E."
    
    res = resolver.resolve(atc_text, [
        "client_name_1_display",
        "client_name_2_display"
    ])
    
    # client_name_1 ("JOHN DOE") should be filtered out because it can't be anchored
    assert "client_name_1_display" not in res
    assert res["client_name_2_display"]["value"] == "RAMAR E"


def test_llm_resolver_openai_compatible():
    resolver = LLMFieldResolver()
    resolver.provider = "openai_compatible"
    resolver.api_key = "sk-FakeOpenAIKeyForTesting"
    resolver.base_url = "https://api.groq.com/openai/v1/chat/completions"
    resolver.model_name = "llama3-70b-8192"
    resolver.enabled = True
    
    # Mock direct _call_openai_compatible method
    resolver._call_openai_compatible = MagicMock(return_value="""
    {
        "payment_terms_supply_pct": 80,
        "payment_terms_installation_pct": 20
    }
    """)
    
    atc_text = "Standard payment split: 80% on delivery, 20% on commissioning."
    
    res = resolver.resolve(atc_text, [
        "payment_terms_supply_display",
        "payment_terms_installation_display"
    ])
    
    assert res["payment_terms_supply_display"]["value"] == "80%"
    assert res["payment_terms_installation_display"]["value"] == "20%"
    resolver._call_openai_compatible.assert_called_once()


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


def test_llm_resolver_anthropic():
    resolver = LLMFieldResolver()
    resolver.provider = "anthropic"
    resolver.api_key = "sk-ant-FakeAnthropicKeyForTesting"
    resolver.model_name = "claude-3-5-sonnet-20241022"
    resolver.enabled = True

    resolver._call_anthropic = MagicMock(return_value="""
    {
        "payment_terms_supply_pct": 75,
        "payment_terms_installation_pct": 25,
        "ld_percentage_per_week": 0.5
    }
    """)

    atc_text = "GAIL payment terms: 75% on supply and 25% on installation. Delay PRS 0.5%."

    res = resolver.resolve(atc_text, [
        "payment_terms_supply_display",
        "payment_terms_installation_display",
        "ld_percentage_display"
    ])

    assert res["payment_terms_supply_display"]["value"] == "75%"
    assert res["payment_terms_installation_display"]["value"] == "25%"
    assert res["ld_percentage_display"]["value"] == "0.5%"
    resolver._call_anthropic.assert_called_once()


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


