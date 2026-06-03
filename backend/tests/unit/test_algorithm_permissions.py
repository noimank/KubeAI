"""Tests for algorithm/RBAC permission seeding."""

import pytest

from app.core.permissions import SEED_POLICIES, SEED_ROLE_INHERITANCE


# Inline enforcer for testing -- simulates the Casbin model logic without a database.
def _build_effective_permissions():
    """Build a map of role -> set of (resource, action) by applying role inheritance."""
    role_policies: dict[str, set[tuple[str, str]]] = {}
    for role, resource, action in SEED_POLICIES:
        role_policies.setdefault(role, set()).add((resource, action))

    # Apply inheritance (parent inherits child's permissions)
    for parent, child in SEED_ROLE_INHERITANCE:
        if child in role_policies:
            role_policies.setdefault(parent, set()).update(role_policies[child])

    return role_policies


@pytest.fixture(scope="module")
def effective_permissions():
    return _build_effective_permissions()


class TestAlgorithmPermissions:
    """Verify algorithm resource permissions are declared correctly."""

    def test_engineer_can_read_algorithms(self, effective_permissions):
        assert ("algorithms", "read") in effective_permissions.get("engineer", set())

    def test_engineer_can_write_algorithms(self, effective_permissions):
        assert ("algorithms", "write") in effective_permissions.get("engineer", set())

    def test_engineer_cannot_manage_algorithms(self, effective_permissions):
        assert ("algorithms", "manage") not in effective_permissions.get("engineer", set())

    def test_mlops_can_manage_algorithms(self, effective_permissions):
        assert ("algorithms", "manage") in effective_permissions.get("mlops", set())

    def test_mlops_can_read_algorithms(self, effective_permissions):
        assert ("algorithms", "read") in effective_permissions.get("mlops", set())

    def test_admin_can_manage_algorithms(self, effective_permissions):
        assert ("algorithms", "manage") in effective_permissions.get("admin", set())

    def test_annotator_cannot_read_algorithms(self, effective_permissions):
        assert ("algorithms", "read") not in effective_permissions.get("annotator", set())

    def test_annotator_cannot_manage_algorithms(self, effective_permissions):
        assert ("algorithms", "manage") not in effective_permissions.get("annotator", set())


class TestPermissionSeedFormat:
    """Verify the seed policy declarations have correct format."""

    def test_all_roles_are_valid(self):
        valid_roles = {"admin", "mlops", "engineer", "annotator"}
        for role, _, _ in SEED_POLICIES:
            assert role in valid_roles, f"Unknown role: {role}"

    def test_all_resources_are_valid(self):
        from app.core.permissions import RESOURCE

        valid_resources = set(RESOURCE.__members__.values())
        for _, resource, _ in SEED_POLICIES:
            assert resource in valid_resources, f"Unknown resource: {resource}"

    def test_all_actions_are_valid(self):
        from app.core.permissions import ACTION

        valid_actions = set(ACTION.__members__.values())
        for _, _, action in SEED_POLICIES:
            assert action in valid_actions, f"Unknown action: {action}"
