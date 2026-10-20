"""Tests for Requirement Quality Checker verifying ambiguity, incompleteness, conflicts, and endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.quality import QualityIssueType, RequirementInput
from app.services.quality_checker import (
    analyze_requirements,
    detect_ambiguity,
    detect_conflict_pairs,
    detect_contradiction_pairs,
    detect_incompleteness,
    detect_inconsistency_pairs,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Ambiguity detection tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("req_id, text, expected_word, check_related", [
    ("R-001", "The system must respond quickly.", "quickly", True),
    ("R-002", "The interface must be user-friendly.", "user-friendly", False),
    ("R-003", "The system should display appropriate information.", "appropriate", False),
    ("R-004", "The system must export data including but not limited to logs.", "including but not limited to", False),
])
def test_ambiguity_positive(req_id, text, expected_word, check_related):
    flags = detect_ambiguity(req_id, text)
    assert len(flags) == 1 and flags[0].type == QualityIssueType.AMBIGUOUS
    assert expected_word.lower() in flags[0].message.lower()
    if check_related:
        assert flags[0].related_requirement_ids == []


# ---------------------------------------------------------------------------
# Incompleteness detection tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("req_id, text, expected_keyword", [
    ("R-010", "Must be updated on submission.", "actor"),
    ("R-011", "The system shall be notified.", "actor"),
    ("R-012", "Someone can view the audit log.", "someone"),
    ("R-013", "Passwords must have a minimum length.", "measurable value"),
    ("R-014", "The session expires after an idle period.", "idle period"),
    ("R-015", "The system sends an email notification if.", "condition"),
    ("R-016", "Under certain conditions, the session terminates.", "under certain conditions"),
])
def test_incompleteness_positive(req_id, text, expected_keyword):
    flags = detect_incompleteness(req_id, text)
    assert len(flags) == 1 and flags[0].type == QualityIssueType.INCOMPLETE
    assert expected_keyword.lower() in flags[0].message.lower()


# ---------------------------------------------------------------------------
# Single-requirement negative / clean tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("detector, req_id, text", [
    (detect_ambiguity, "R-005", "The system must display the user's active subscriptions."),
    (detect_ambiguity, "R-006", "The user enters a 6-digit numeric verification code."),
    (detect_ambiguity, "R-007", "The system responds within 500 milliseconds."),
    (detect_incompleteness, "R-017", "The system must allow guest checkout."),
    (detect_incompleteness, "R-018", "Users can download invoice receipts."),
    (detect_incompleteness, "R-019", "The administrator can deactivate user accounts."),
])
def test_single_requirement_negatives(detector, req_id, text):
    assert detector(req_id, text) == []


# ---------------------------------------------------------------------------
# Pair conflict tests (unified conflict category: values & behaviors)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("detector, requirements, id1, id2, expected_in_message", [
    (detect_inconsistency_pairs, [
        {"id": "R1", "text": "The session expires after 15 minutes."},
        {"id": "R2", "text": "The session expires after 30 minutes."},
    ], "R1", "R2", ["15 minutes", "30 minutes"]),
    (detect_conflict_pairs, [
        {"id": "R-101", "text": "Log files are retained for 30 days."},
        {"id": "R-102", "text": "Log files are retained for 90 days."},
    ], "R-101", "R-102", []),
    (detect_contradiction_pairs, [
        {"id": "R1", "text": "The system must allow guest checkout."},
        {"id": "R2", "text": "The system must not allow guest checkout."},
    ], "R1", "R2", ["must allow"]),
    (detect_conflict_pairs, [
        {"id": "R1", "text": "Enable two-factor authentication by default."},
        {"id": "R2", "text": "Disable two-factor authentication by default."},
    ], "R1", "R2", []),
])
def test_pair_conflicts_positive(detector, requirements, id1, id2, expected_in_message):
    flags = detector(requirements)
    assert len(flags) == 2
    flag1, flag2 = next(f for f in flags if f.requirement_id == id1), next(f for f in flags if f.requirement_id == id2)
    assert flag1.type == QualityIssueType.CONFLICT and flag2.type == QualityIssueType.CONFLICT
    assert flag1.related_requirement_ids == [id2] and flag2.related_requirement_ids == [id1]
    for text in expected_in_message:
        assert text.lower() in flag1.message.lower()


@pytest.mark.parametrize("detector, requirements", [
    (detect_inconsistency_pairs, [{"id": "R1", "text": "The session expires after 15 minutes."}, {"id": "R2", "text": "The session expires after 15 minutes."}]),
    (detect_inconsistency_pairs, [{"id": "R1", "text": "The session expires after 15 minutes."}, {"id": "R2", "text": "Passwords expire after 90 days."}]),
    (detect_inconsistency_pairs, [{"id": "R1", "text": "For mobile users, the session expires after 15 minutes."}, {"id": "R2", "text": "For desktop users, the session expires after 30 minutes."}]),
    (detect_contradiction_pairs, [{"id": "R1", "text": "The system must allow guest checkout."}, {"id": "R2", "text": "The system allows guest checkout."}]),
    (detect_contradiction_pairs, [{"id": "R1", "text": "Admins can delete user accounts."}, {"id": "R2", "text": "Standard users cannot delete user accounts."}]),
    (detect_contradiction_pairs, [{"id": "R1", "text": "When online, transactions are processed immediately."}, {"id": "R2", "text": "When offline, transactions are queued."}]),
    (detect_contradiction_pairs, [{"id": "R1", "text": "The system must allow guest checkout."}, {"id": "R2", "text": "The system must not allow unauthenticated admin access."}]),
])
def test_pair_negatives(detector, requirements):
    assert detector(requirements) == []


# ---------------------------------------------------------------------------
# Combined analysis tests
# ---------------------------------------------------------------------------
def test_analyze_requirements_full():
    requirements = [
        RequirementInput(id="R01", text="The system must respond quickly."),
        RequirementInput(id="R02", text="The interface must be user-friendly."),
        RequirementInput(id="R03", text="The system should display appropriate information."),
        RequirementInput(id="R04", text="Must be updated on submission."),
        RequirementInput(id="R05", text="The system shall be notified."),
        RequirementInput(id="R06", text="Someone can view the audit log."),
        RequirementInput(id="R07", text="Passwords must have a minimum length."),
        RequirementInput(id="R10", text="The session expires after 15 minutes."),
        RequirementInput(id="R11", text="The session expires after 30 minutes."),
        RequirementInput(id="R12", text="The system must allow guest checkout."),
        RequirementInput(id="R13", text="The system must not allow guest checkout."),
    ]
    response = analyze_requirements(requirements)
    assert len(response.overview) == 9
    assert response.total_flags == 11
    assert response.summary == {"ambiguous": 3, "incomplete": 4, "conflict": 2}
    assert "R10, R11: conflict" in response.overview
    assert "R11, R10: conflict" not in response.overview
    assert "R12, R13: conflict" in response.overview
    assert "R13, R12: conflict" not in response.overview
    flag_ids = [f.requirement_id for f in response.flags]
    assert "R10" in flag_ids and "R11" in flag_ids and "R12" in flag_ids and "R13" in flag_ids
    flag_r10, flag_r11 = next(f for f in response.flags if f.requirement_id == "R10"), next(f for f in response.flags if f.requirement_id == "R11")
    assert flag_r10.type == QualityIssueType.CONFLICT and flag_r11.type == QualityIssueType.CONFLICT
    assert flag_r10.related_requirement_ids == ["R11"] and flag_r11.related_requirement_ids == ["R10"]
    flag_r12, flag_r13 = next(f for f in response.flags if f.requirement_id == "R12"), next(f for f in response.flags if f.requirement_id == "R13")
    assert flag_r12.type == QualityIssueType.CONFLICT and flag_r13.type == QualityIssueType.CONFLICT
    assert flag_r12.related_requirement_ids == ["R13"] and flag_r13.related_requirement_ids == ["R12"]


def test_two_conflict_pairs_produce_four_flags_and_two_issues():
    requirements = [
        {"id": "R10", "text": "The session expires after 15 minutes."},
        {"id": "R11", "text": "The session expires after 30 minutes."},
        {"id": "R12", "text": "The system must allow guest checkout."},
        {"id": "R13", "text": "The system must not allow guest checkout."},
    ]
    response = analyze_requirements(requirements)
    assert response.total_flags == 4
    assert len(response.flags) == 4
    assert response.summary["conflict"] == 2
    assert len(response.overview) == 2
    assert "R10, R11: conflict" in response.overview
    assert "R12, R13: conflict" in response.overview


@pytest.mark.parametrize("requirements, expected_total", [
    ([{"id": "R1", "text": "The session expires after 15 minutes."}, {"id": "R2", "text": "The session expires after 30 minutes."}], 2),
    ([{"id": "R11", "text": "The session expires after 30 minutes."}, {"id": "R10", "text": "The session expires after 15 minutes."}], 2),
    ([], 0),
    ([{"id": "R1", "text": "   "}, {"id": "R2", "text": ""}], 0),
    ([{"id": "R1", "text": "The system must allow guest checkout."}, {"id": "R2", "text": "Users can download invoice receipts."},
      {"id": "R3", "text": "The administrator can deactivate user accounts."}, {"id": "R4", "text": "The session expires after 15 minutes."}], 0),
])
def test_analyze_requirements_edge_cases(requirements, expected_total):
    response = analyze_requirements(requirements)
    assert response.total_flags == expected_total
    if not expected_total:
        assert response.flags == [] and all(count == 0 for count in response.summary.values())
    else:
        assert len(response.flags) == 2 and response.flags[0].type == QualityIssueType.CONFLICT
        assert response.summary["conflict"] == 1
        assert len(response.overview) == 1


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------
def test_endpoint_quality_check_success(client):
    payload = {"requirements": [
        {"id": "R-001", "text": "The system must respond quickly."},
        {"id": "R-002", "text": "The session expires after 15 minutes."},
        {"id": "R-003", "text": "The session expires after 30 minutes."},
    ]}
    response = client.post("/api/v1/quality/check", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "flags" in data and data["total_flags"] == 3
    assert data["summary"]["ambiguous"] == 1 and data["summary"]["conflict"] == 1
    assert len(data["overview"]) == 2


def test_endpoint_empty_input(client):
    response = client.post("/api/v1/quality/check", json={"requirements": []})
    assert response.status_code == 200
    data = response.json()
    assert data["flags"] == [] and data["total_flags"] == 0
