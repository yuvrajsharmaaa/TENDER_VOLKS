import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(".env.dev")

from backend.app.services.llm_field_resolver import LLMFieldResolver

resolver = LLMFieldResolver()
print("Initialized LLMFieldResolver with model:", resolver.model_name)

test_text = """
PAYMENT TERMS:
GAIL shall release 70% Payment of Supply portion on receipt of material at GAIL site and Acceptance by GAIL.
The remaining 30% payment of supply portion and payment of installation & commissioning charges shall be released after completion.

CLIENT CONTACTS:
Nodal Officer: Shri Prabhakar Deevi, DGM (HR)
Tel: 0883-2400720
Email: prabhakar.deevi@gail.co.in
"""

missing_keys = ["payment_terms_supply_display", "payment_terms_installation_display", "client_name_2_display", "client_email_2_display"]

resolved = resolver.resolve(test_text, missing_keys)
print("\nResolved fields:")
for k, v in resolved.items():
    print(f"  {k}: {v!r}")
