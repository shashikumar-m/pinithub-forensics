"""Run Phase 7 evaluation and print summary."""
from app.travel.evaluation import run_evaluation
import json

result = run_evaluation()

print("=== Phase 7 Evaluation Results ===")
print(f"Total cases: {result['total_cases']}")
print(f"Failed: {result['failed']}")
print()

neg = result['negative_controls']
print(f"Negative controls: {neg['count']} tested")
print(f"  FP rate: {neg['false_positive_rate']:.2%} ({neg['false_positives']} FP)")
print(f"  Note: {neg['note']}")
print()

trans = result['transport_only']
print(f"Transport-only: {trans['count']} tested")
print(f"  FP rate: {trans['false_positive_rate']:.2%} ({trans['false_positives']} FP)")
print(f"  Note: {trans['note']}")
print()

content = result['content_changes']
print(f"Content changes: {content['count']} tested")
print(f"  Detection rate: {content['detection_rate']:.2%}")
print()

print("Robustness matrix:")
for name, vals in result['robustness_matrix'].items():
    transforms = vals.get('detected_transforms', [])
    print(f"  {name:35s} -> {vals['detected_status']:28s} {transforms}")

print()
print(result['note'])
