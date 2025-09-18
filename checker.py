#!/usr/bin/env python3
"""
Script to validate links in links.json against annotations in pdf_pairs.json.
Focuses on reporting ONLY issues that need fixing, grouped by type.
Checks for:
- Invalid links (missing selection IDs)
- Warnings (duplicates, mismatched PDF types, pair mismatches)
- Rule violations (stems with answers or stem links)
- Stem markings inconsistencies

To aid fixing:
- Suggests specific actions for each issue
- Groups issues for easy scanning

Usage: python validate_links.py
Assumes pdf_pairs.json and links.json in current directory.
"""

import json
import os

def main():
    pdf_pairs_file = "pdf_pairs.json"
    links_file = "links.json"

    if not os.path.exists(pdf_pairs_file):
        print(f"Error: {pdf_pairs_file} not found.")
        return

    if not os.path.exists(links_file):
        print(f"Error: {links_file} not found.")
        return

    # Load data
    with open(pdf_pairs_file, 'r') as f:
        pairs_data = json.load(f)

    with open(links_file, 'r') as f:
        links_data = json.load(f)

    # Build mapping: selection_id -> list of (pair_id, pdf_type, page)
    id_to_locs = {}
    for pair_id, pair in pairs_data.get('pairs', {}).items():
        for pdf_type, anns in [("pdf1", pair.get("pdf1_annotations", {})), ("pdf2", pair.get("pdf2_annotations", {}))]:
            for page_str, page_anns in anns.items():
                for ann in page_anns:
                    sel_id = ann.get("selection_id")
                    page = ann.get("page")  # 1-based
                    if sel_id:
                        if sel_id not in id_to_locs:
                            id_to_locs[sel_id] = []
                        id_to_locs[sel_id].append((pair_id, pdf_type, page))

    # Collect issues
    invalid_links = []  # Missing IDs
    warnings = []       # Duplicates, mismatches
    violations = []     # Rule breaks

    # Find duplicates globally
    for sel_id, locs in id_to_locs.items():
        if len(locs) > 1:
            warnings.append({
                'type': 'duplicate_id',
                'id': sel_id,
                'locations': locs,
                'suggestion': f"Resolve duplicates for {sel_id}. Ensure unique IDs across all pairs."
            })

    questions = links_data.get("questions", {})
    if not questions:
        print("No questions/links found in links.json. Nothing to validate.")
        return

    for question_id, data in questions.items():
        q_locs = id_to_locs.get(question_id, [])
        if not q_locs:
            invalid_links.append({
                'id': question_id,
                'issue': 'Missing question ID in annotations.',
                'suggestion': f"Remove entry for {question_id} from links.json or add missing annotation."
            })
            continue

        # Use first location, collect warnings if multiple or wrong type/pair
        q_loc = q_locs[0]
        if len(q_locs) > 1:
            warnings.append({
                'type': 'duplicate_question',
                'id': question_id,
                'locations': q_locs,
                'suggestion': f"Resolve duplicate locations for question {question_id}."
            })

        if q_loc[1] != "pdf1":
            warnings.append({
                'type': 'wrong_pdf_type',
                'id': question_id,
                'current': q_loc[1],
                'location': f"Pair {q_loc[0]}, page {q_loc[2]}",
                'suggestion': f"Move {question_id} to pdf1 or update link."
            })

        # Check answer
        answer_id = data.get("answer")
        if answer_id:
            a_locs = id_to_locs.get(answer_id, [])
            if not a_locs:
                invalid_links.append({
                    'id': answer_id,
                    'issue': f"Missing answer ID linked from question {question_id}.",
                    'question_loc': f"Pair {q_loc[0]}, pdf1, page {q_loc[2]}",
                    'suggestion': f"Remove 'answer' from {question_id} in links.json or add missing annotation."
                })
            else:
                a_loc = a_locs[0]
                if len(a_locs) > 1:
                    warnings.append({
                        'type': 'duplicate_answer',
                        'id': answer_id,
                        'locations': a_locs,
                        'suggestion': f"Resolve duplicates for answer {answer_id} linked from {question_id}."
                    })
                if a_loc[1] != "pdf2":
                    warnings.append({
                        'type': 'wrong_pdf_type',
                        'id': answer_id,
                        'current': a_loc[1],
                        'location': f"Pair {a_loc[0]}, page {a_loc[2]}",
                        'suggestion': f"Move answer {answer_id} to pdf2 or update link for question {question_id}."
                    })
                if a_loc[0] != q_loc[0]:
                    warnings.append({
                        'type': 'pair_mismatch',
                        'id': answer_id,
                        'question_pair': q_loc[0],
                        'answer_pair': a_loc[0],
                        'suggestion': f"Move answer {answer_id} to pair {q_loc[0]} or update link."
                    })

        # Check stem
        stem_id = data.get("stem")
        if stem_id:
            s_locs = id_to_locs.get(stem_id, [])
            if not s_locs:
                invalid_links.append({
                    'id': stem_id,
                    'issue': f"Missing stem ID linked from question {question_id}.",
                    'question_loc': f"Pair {q_loc[0]}, pdf1, page {q_loc[2]}",
                    'suggestion': f"Remove 'stem' from {question_id} in links.json or add missing annotation."
                })
            else:
                s_loc = s_locs[0]
                if len(s_locs) > 1:
                    warnings.append({
                        'type': 'duplicate_stem',
                        'id': stem_id,
                        'locations': s_locs,
                        'suggestion': f"Resolve duplicates for stem {stem_id} linked from {question_id}."
                    })
                if s_loc[1] != "pdf1":
                    warnings.append({
                        'type': 'wrong_pdf_type',
                        'id': stem_id,
                        'current': s_loc[1],
                        'location': f"Pair {s_loc[0]}, page {s_loc[2]}",
                        'suggestion': f"Move stem {stem_id} to pdf1 or update link for {question_id}."
                    })
                if s_loc[0] != q_loc[0]:
                    warnings.append({
                        'type': 'pair_mismatch',
                        'id': stem_id,
                        'question_pair': q_loc[0],
                        'stem_pair': s_loc[0],
                        'suggestion': f"Move stem {stem_id} to pair {q_loc[0]} or update link."
                    })

                # Check stem marking
                stem_data = questions.get(stem_id, {})
                if not stem_data.get("isStem"):
                    warnings.append({
                        'type': 'missing_isStem',
                        'id': stem_id,
                        'linked_from': question_id,
                        'location': f"Pair {s_loc[0]}, pdf1, page {s_loc[2]}",
                        'suggestion': f"Add 'isStem': true to {stem_id} in links.json."
                    })

        # Rule checks for isStem
        if data.get("isStem"):
            if answer_id:
                violations.append({
                    'id': question_id,
                    'issue': f"Stem has answer {answer_id}.",
                    'location': f"Pair {q_loc[0]}, pdf1, page {q_loc[2]}",
                    'suggestion': f"Remove 'answer' from stem {question_id} in links.json."
                })
            if stem_id:
                violations.append({
                    'id': question_id,
                    'issue': f"Stem linked to another stem {stem_id}.",
                    'location': f"Pair {q_loc[0]}, pdf1, page {q_loc[2]}",
                    'suggestion': f"Remove 'stem' from {question_id} in links.json."
                })

    # Report issues only
    print("\n=== Validation Report ===")
    if not (invalid_links or warnings or violations):
        print("All links are valid. No issues found.")
        return

    if invalid_links:
        print("\nINVALID LINKS (Missing IDs - These need immediate fixing):")
        for issue in invalid_links:
            print(f"- ID: {issue['id']}")
            print(f"  Issue: {issue['issue']}")
            if 'question_loc' in issue:
                print(f"  Related Location: {issue['question_loc']}")
            print(f"  Suggestion: {issue['suggestion']}")
            print()

    if warnings:
        print("\nWARNINGS (Mismatches/Duplicates - Review and fix):")
        for issue in warnings:
            print(f"- Type: {issue['type'].replace('_', ' ').title()}")
            print(f"  ID: {issue['id']}")
            if 'locations' in issue:
                print("  Locations:")
                for loc in issue['locations']:
                    print(f"    - Pair {loc[0]}, {loc[1]}, page {loc[2]}")
            if 'current' in issue:
                print(f"  Current: {issue['current']}")
            if 'location' in issue:
                print(f"  Location: {issue['location']}")
            if 'question_pair' in issue:
                print(f"  Question Pair: {issue['question_pair']}")
                print(f"  Other Pair: {issue.get('answer_pair') or issue.get('stem_pair')}")
            if 'linked_from' in issue:
                print(f"  Linked from: {issue['linked_from']}")
            print(f"  Suggestion: {issue['suggestion']}")
            print()

    if violations:
        print("\nRULE VIOLATIONS (Breaks app rules - Must fix):")
        for issue in violations:
            print(f"- ID: {issue['id']}")
            print(f"  Issue: {issue['issue']}")
            print(f"  Location: {issue['location']}")
            print(f"  Suggestion: {issue['suggestion']}")
            print()

    print("\nEnd of report. Fix suggestions provided for each issue.")

if __name__ == "__main__":
    main()