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
    resolver.api_key = "AIzaSyRealKeyStyleForTesting"
    resolver.enabled = True
    
    mock_json = """
    {
        "client_name_1": "JOHN DOE",
        "client_name_2": "RAMAR E"
    }
    """
    resolver._call_gemini_v2 = MagicMock(return_value=mock_json)
    
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


