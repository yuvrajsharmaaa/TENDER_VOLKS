import sys
import argparse
import logging
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.repositories.dlq_repository import (
    list_dead_letter_envelopes,
    get_dead_letter_envelope,
    update_dlq_status
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dlq_tool")


def cmd_list(args):
    items = list_dead_letter_envelopes(status=args.status, limit=args.limit)
    print("\n" + "="*80)
    print(f"DEAD LETTER QUEUE (DLQ) ENVELOPES (Total: {len(items)}, Filter: {args.status or 'ALL'})")
    print("="*80)
    if not items:
        print("No dead-letter envelopes found.")
        return
        
    print(f"{'DLQ ID':<38} | {'STATUS':<10} | {'ATTEMPTS':<8} | {'TASK NAME':<18} | {'ERROR TYPE'}")
    print("-" * 80)
    for it in items:
        print(f"{it.dlq_id:<38} | {it.status:<10} | {it.attempt_count:<8} | {it.task_name:<18} | {it.error_type}")
    print("="*80 + "\n")


def cmd_get(args):
    item = get_dead_letter_envelope(args.dlq_id)
    if not item:
        print(f"Error: DLQ Envelope '{args.dlq_id}' not found.")
        sys.exit(1)
        
    print("\n" + "="*80)
    print(f"DLQ ENVELOPE: {item.dlq_id}")
    print("="*80)
    print(f"Status           : {item.status}")
    print(f"Task ID          : {item.task_id}")
    print(f"Task Name        : {item.task_name}")
    print(f"Attempts         : {item.attempt_count}")
    print(f"Error Type       : {item.error_type}")
    print(f"Error Message    : {item.error_message}")
    print(f"Resolution Notes : {item.resolution_notes or 'None'}")
    print(f"Created At       : {item.created_at}")
    print(f"Updated At       : {item.updated_at}")
    print(f"Payload          : {item.payload}")
    if item.stack_trace:
        print(f"\n--- Stack Trace ---\n{item.stack_trace}")
    print("="*80 + "\n")


def cmd_replay(args):
    item = get_dead_letter_envelope(args.dlq_id)
    if not item:
        print(f"Error: DLQ Envelope '{args.dlq_id}' not found.")
        sys.exit(1)
        
    updated = update_dlq_status(args.dlq_id, status="REPLAYED", resolution_notes="Replay triggered via dlq_tool CLI")
    print(f"Successfully replayed DLQ envelope '{args.dlq_id}' (Status: {updated.status}).")


def cmd_discard(args):
    if not args.notes or len(args.notes.strip()) < 10:
        print("Error: Substantive resolution notes (>= 10 characters) are strictly required to discard a failed task.")
        sys.exit(1)
        
    try:
        updated = update_dlq_status(args.dlq_id, status="DISCARDED", resolution_notes=args.notes.strip())
        print(f"Successfully marked DLQ envelope '{args.dlq_id}' as DISCARDED.")
        print(f"Resolution Notes: '{updated.resolution_notes}'")
    except ValueError as e:
        print(f"Validation Error: {e}")
        sys.exit(1)


def cmd_replay_batch(args):
    items = list_dead_letter_envelopes(status=args.status, limit=args.limit)
    if not items:
        print("No envelopes matching filter to replay.")
        return
        
    replayed = 0
    for it in items:
        try:
            update_dlq_status(it.dlq_id, status="REPLAYED", resolution_notes="Batch replay triggered via dlq_tool CLI")
            replayed += 1
        except Exception as e:
            print(f"Failed to replay {it.dlq_id}: {e}")
    print(f"Batch replay complete: {replayed}/{len(items)} envelopes marked REPLAYED.")


def main():
    parser = argparse.ArgumentParser(description="Tender Volks — Dead Letter Queue (DLQ) Operational CLI Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # list
    p_list = subparsers.add_parser("list", help="List DLQ items")
    p_list.add_argument("--status", choices=["PENDING", "REPLAYED", "DISCARDED", "RESOLVED"], help="Filter by status")
    p_list.add_argument("--limit", type=int, default=50, help="Max items to display")
    p_list.set_defaults(func=cmd_list)
    
    # get
    p_get = subparsers.add_parser("get", help="Get full envelope details")
    p_get.add_argument("dlq_id", help="DLQ Envelope ID")
    p_get.set_defaults(func=cmd_get)
    
    # replay
    p_replay = subparsers.add_parser("replay", help="Replay a single DLQ task")
    p_replay.add_argument("dlq_id", help="DLQ Envelope ID to replay")
    p_replay.set_defaults(func=cmd_replay)
    
    # discard
    p_discard = subparsers.add_parser("discard", help="Discard a DLQ task with required resolution notes")
    p_discard.add_argument("dlq_id", help="DLQ Envelope ID to discard")
    p_discard.add_argument("--notes", "-n", required=True, help="Mandatory substantive explanation (>= 10 chars)")
    p_discard.set_defaults(func=cmd_discard)
    
    # replay-batch
    p_batch = subparsers.add_parser("replay-batch", help="Replay batch of DLQ tasks")
    p_batch.add_argument("--status", default="PENDING", help="Filter status for batch replay")
    p_batch.add_argument("--limit", type=int, default=50, help="Batch limit")
    p_batch.set_defaults(func=cmd_replay_batch)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
