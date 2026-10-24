"""Company endpoints and the negative security matrix (docs/SECURITY.md § 2).

Requests run as the runtime role inside the view's transaction (``tenancy`` switches the
owner test connection to it), so row-level security applies to every query of the view.
After every request the connection must carry no tenant context.
Commit/rollback behaviour is covered with real transactions in test_company_transactions.py.
"""

import uuid

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.events import AuditEvent, Outcome
from apps.audit.models import AuditLog
from apps.core import tenancy
from apps.organizations.access import COMPANY_ACCESS_DENIED_PER_USER
from apps.organizations.models import Branch
from apps.organizations.tests.factories import World, build_world, signed_in
from apps.tenants.models import Membership, Tenant

pytestmark = pytest.mark.django_db

OWNER = settings.DATABASES["default"]["USER"]


@pytest.fixture
def world() -> World:
    return build_world()


def assert_no_tenant_context() -> None:
    assert tenancy.current() == ("", "", OWNER)


def get_active(client: APIClient, company_id=None, **headers):
    if company_id is not None:
        headers["HTTP_X_COMPANY_ID"] = str(company_id)
    response = client.get(reverse("company-active"), **headers)
    assert_no_tenant_context()
    return response


def error_without_request_id(response) -> dict:
    error = dict(response.json()["error"])
    error.pop("request_id", None)
    return error


# --- listing companies ----------------------------------------------------------------------


def test_list_shows_only_active_companies_of_active_memberships(world):
    response = signed_in(world.alice).get(reverse("company-list"))

    assert response.status_code == 200
    # Not A2 (inactive), B1 (no membership), C1 (membership disabled), S1 (tenant suspended).
    assert [c["id"] for c in response.json()] == [str(world.company_a1.pk)]
    assert response.json()[0]["tenant"] == {"id": str(world.tenant_a.pk), "name": "Tenant A"}
    assert_no_tenant_context()


def test_list_spans_all_tenants_of_the_user(world):
    response = signed_in(world.carol).get(reverse("company-list"))

    assert {c["code"] for c in response.json()} == {"A1", "B1"}


def test_list_requires_authentication(world):
    assert APIClient().get(reverse("company-list")).status_code == 403


# --- active company: allowed ----------------------------------------------------------------


def test_active_company_resolves_from_the_header(world):
    response = get_active(signed_in(world.alice), world.company_a1.pk)

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["code"], body["base_currency_code"]) == (
        str(world.company_a1.pk),
        "A1",
        "USD",
    )


def test_uppercase_uuid_is_accepted(world):
    response = get_active(signed_in(world.alice), str(world.company_a1.pk).upper())

    assert response.status_code == 200


def test_user_with_two_tenants_switches_per_request(world):
    client = signed_in(world.carol)
    for company in (world.company_a1, world.company_b1, world.company_a1):
        response = get_active(client, company.pk)
        assert response.json()["id"] == str(company.pk)


# --- active company: header problems → 400 ----------------------------------------------------


def test_missing_header(world):
    response = get_active(signed_in(world.alice))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "company_required"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-uuid",
        "{a1},{b1}",
        " {a1}",
        "{a1} ",
        "{a1_hex}",
        "{a1}0",
        "{{{a1}}}",
        "urn:uuid:{a1}",
    ],
)
def test_malformed_header(world, value):
    a1 = world.company_a1.pk
    header = value.format(a1=a1, b1=world.company_b1.pk, a1_hex=a1.hex)

    response = get_active(signed_in(world.alice), HTTP_X_COMPANY_ID=header)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "company_required"
    assert str(a1) not in response.content.decode()


# --- active company: no access → identical 404 ----------------------------------------------


def test_every_kind_of_inaccessible_company_gives_the_same_404(world):
    client = signed_in(world.alice)
    inaccessible = {
        "other tenant": world.company_b1.pk,
        "random id": uuid.uuid4(),
        "inactive company": world.company_a2.pk,
        "disabled membership": world.company_c1.pk,
        "suspended tenant": world.company_s1.pk,
    }

    errors = {}
    for case, company_id in inaccessible.items():
        response = get_active(client, company_id)
        assert response.status_code == 404, case
        errors[case] = error_without_request_id(response)

    assert len({str(e) for e in errors.values()}) == 1
    assert errors["random id"]["code"] == "not_found"


def test_session_of_one_user_with_company_of_another(world):
    assert get_active(signed_in(world.bob), world.company_a1.pk).status_code == 404


def test_disabled_membership_takes_effect_on_the_next_request(world):
    client = signed_in(world.carol)
    assert get_active(client, world.company_b1.pk).status_code == 200

    Membership.objects.filter(pk=world.membership_carol_b.pk).update(
        status=Membership.Status.DISABLED
    )

    assert get_active(client, world.company_b1.pk).status_code == 404
    assert get_active(client, world.company_a1.pk).status_code == 200  # other tenant unaffected


def test_suspended_tenant_takes_effect_on_the_next_request(world):
    client = signed_in(world.alice)
    assert get_active(client, world.company_a1.pk).status_code == 200

    Tenant.objects.filter(pk=world.tenant_a.pk).update(status=Tenant.Status.SUSPENDED)

    assert get_active(client, world.company_a1.pk).status_code == 404


def test_deactivated_user_loses_the_session(world):
    client = signed_in(world.alice)
    type(world.alice).objects.filter(pk=world.alice.pk).update(is_active=False)

    assert get_active(client, world.company_a1.pk).status_code == 403


def test_unauthenticated_request_is_rejected_before_company_resolution(world):
    response = get_active(APIClient(), world.company_a1.pk)

    assert response.status_code == 403
    assert not AuditLog.objects.filter(event_type=AuditEvent.COMPANY_ACCESS_DENIED).exists()


# --- request parameters cannot choose the company -------------------------------------------


def test_query_parameters_are_ignored(world):
    client = signed_in(world.alice)
    response = client.get(
        reverse("company-active") + f"?company_id={world.company_b1.pk}"
        f"&tenant_id={world.tenant_b.pk}",
        HTTP_X_COMPANY_ID=str(world.company_a1.pk),
    )

    assert response.json()["id"] == str(world.company_a1.pk)


def test_body_fields_are_ignored(world):
    response = signed_in(world.alice).post(
        reverse("company-select"),
        {"company_id": str(world.company_b1.pk), "tenant_id": str(world.tenant_b.pk)},
        format="json",
        HTTP_X_COMPANY_ID=str(world.company_a1.pk),
    )

    assert response.json()["id"] == str(world.company_a1.pk)
    event = AuditLog.objects.get(event_type=AuditEvent.COMPANY_SELECTED)
    assert (event.tenant_id, event.company_id) == (world.tenant_a.pk, world.company_a1.pk)


def test_header_is_ignored_by_endpoints_that_are_not_company_scoped(world):
    response = signed_in(world.alice).get(reverse("auth-me"), HTTP_X_COMPANY_ID="garbage")

    assert response.status_code == 200


# --- selecting a company (audited) ----------------------------------------------------------


def test_select_records_the_switch(world):
    response = signed_in(world.alice).post(
        reverse("company-select"), HTTP_X_COMPANY_ID=str(world.company_a1.pk)
    )

    assert response.status_code == 200
    [event] = AuditLog.objects.filter(event_type=AuditEvent.COMPANY_SELECTED)
    assert event.outcome == Outcome.SUCCESS
    assert event.actor_id == world.alice.pk
    assert (event.tenant_id, event.company_id) == (world.tenant_a.pk, world.company_a1.pk)
    assert (event.target_type, event.target_id) == ("company", str(world.company_a1.pk))
    assert event.metadata == {}
    assert_no_tenant_context()


def test_select_needs_a_csrf_token(world):
    client = signed_in(world.alice, enforce_csrf_checks=True)
    headers = {"HTTP_X_COMPANY_ID": str(world.company_a1.pk)}

    response = client.post(reverse("company-select"), **headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"

    client.get(reverse("auth-csrf"))
    token = client.cookies["csrftoken"].value
    response = client.post(reverse("company-select"), HTTP_X_CSRFTOKEN=token, **headers)
    assert response.status_code == 200


def test_denied_access_is_audited_without_revealing_the_tenant(world):
    response = get_active(signed_in(world.alice), world.company_b1.pk)

    assert response.status_code == 404
    [event] = AuditLog.objects.filter(event_type=AuditEvent.COMPANY_ACCESS_DENIED)
    assert event.outcome == Outcome.DENIED
    assert (event.tenant_id, event.company_id) == (None, None)
    assert (event.target_type, event.target_id) == ("company", str(world.company_b1.pk))
    assert event.metadata == {"reason": "not_accessible"}


def test_denied_access_is_rate_limited_per_user(world, pinned_rate_limit_clock):
    alice = signed_in(world.alice)
    limit = COMPANY_ACCESS_DENIED_PER_USER.limit

    statuses = [get_active(alice, uuid.uuid4()).status_code for _ in range(limit + 2)]

    assert statuses == [404] * limit + [429, 429]
    assert AuditLog.objects.filter(event_type=AuditEvent.COMPANY_ACCESS_DENIED).count() == limit
    assert AuditLog.objects.filter(event_type=AuditEvent.COMPANY_ACCESS_THROTTLED).count() == 1
    # Allowed requests never count, and other users are not affected.
    assert get_active(alice, world.company_a1.pk).status_code == 200
    assert get_active(signed_in(world.bob), uuid.uuid4()).status_code == 404


def test_throttled_response_has_retry_after(world, pinned_rate_limit_clock):
    alice = signed_in(world.alice)
    for _ in range(COMPANY_ACCESS_DENIED_PER_USER.limit):
        get_active(alice, uuid.uuid4())

    response = get_active(alice, uuid.uuid4())

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
    assert int(response["Retry-After"]) > 0


# --- defence in depth inside a company-scoped view ------------------------------------------


@pytest.mark.urls("apps.organizations.tests.urls")
def test_company_scoping_requires_a_user_even_with_loose_permissions(world):
    headers = {"HTTP_X_COMPANY_ID": str(world.company_a1.pk)}

    anonymous = APIClient().get(reverse("test-loose-permissions"), **headers)
    signed = signed_in(world.alice).get(reverse("test-loose-permissions"), **headers)

    assert anonymous.status_code == 403
    assert anonymous.json()["error"]["code"] == "not_authenticated"
    assert signed.json() == {"company": str(world.company_a1.pk)}
    assert not AuditLog.objects.filter(event_type=AuditEvent.COMPANY_ACCESS_DENIED).exists()
    assert_no_tenant_context()


@pytest.mark.urls("apps.organizations.tests.urls")
def test_forgotten_tenant_filter_still_sees_only_the_active_tenant(world):
    response = signed_in(world.alice).get(
        reverse("test-forgotten-filter"), HTTP_X_COMPANY_ID=str(world.company_a1.pk)
    )

    assert response.json() == sorted([str(world.company_a1.pk), str(world.company_a2.pk)])
    assert_no_tenant_context()


@pytest.mark.urls("apps.organizations.tests.urls")
def test_write_into_another_tenant_is_rejected_by_the_database(world):
    client = signed_in(world.alice, raise_request_exception=False)

    response = client.post(
        reverse("test-cross-tenant"),
        {"tenant_id": str(world.tenant_b.pk), "company_id": str(world.company_b1.pk)},
        format="json",
        HTTP_X_COMPANY_ID=str(world.company_a1.pk),
    )

    assert response.status_code == 500
    assert not Branch.objects.filter(code="EVIL").exists()
    assert_no_tenant_context()


@pytest.mark.urls("apps.organizations.tests.urls")
def test_writes_commit_with_the_success_and_roll_back_with_an_error(world):
    client = signed_in(world.alice)
    headers = {"HTTP_X_COMPANY_ID": str(world.company_a1.pk)}

    ok = client.post(reverse("test-create-branch"), {"code": "OK"}, format="json", **headers)
    failed = client.post(
        reverse("test-create-branch") + "?fail=1", {"code": "NO"}, format="json", **headers
    )

    assert (ok.status_code, failed.status_code) == (201, 400)
    created = Branch.objects.get(pk=ok.json()["id"])
    assert (created.tenant_id, created.company_id) == (world.tenant_a.pk, world.company_a1.pk)
    assert not Branch.objects.filter(code="NO").exists()
    assert_no_tenant_context()
