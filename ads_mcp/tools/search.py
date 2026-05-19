# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tools for exposing the API Search method to the MCP server."""

from typing import Any, Dict, List
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils

from google.ads.googleads.errors import GoogleAdsException


# Cache discovered parent MCC per client customer for the process lifetime.
_parent_mcc_cache: dict[str, str] = {}


def _is_user_permission_denied(exc: GoogleAdsException) -> bool:
    try:
        for err in exc.failure.errors:
            if err.error_code.authorization_error:
                return True
    except Exception:
        pass
    return False


def _discover_parent_mcc(customer_id: str) -> str | None:
    """Walk accessible MCCs to find one that manages customer_id.

    Returns the MCC id (login_customer_id) or None if not found.
    """
    if customer_id in _parent_mcc_cache:
        return _parent_mcc_cache[customer_id]

    customer_service = utils.get_googleads_service("CustomerService")
    try:
        accessible = customer_service.list_accessible_customers()
    except Exception as e:
        utils.logger.warning(f"list_accessible_customers failed: {e}")
        return None

    mcc_ids = [
        rn.removeprefix("customers/") for rn in accessible.resource_names
    ]

    for mcc_id in mcc_ids:
        if mcc_id == customer_id:
            continue
        try:
            ga_service = utils.get_googleads_service(
                "GoogleAdsService", login_customer_id=mcc_id
            )
            query = (
                "SELECT customer_client.id FROM customer_client "
                f"WHERE customer_client.id = {customer_id}"
            )
            stream = ga_service.search_stream(
                customer_id=mcc_id, query=query
            )
            for batch in stream:
                for row in batch.results:
                    if str(row.customer_client.id) == str(customer_id):
                        _parent_mcc_cache[customer_id] = mcc_id
                        utils.logger.info(
                            f"Discovered parent MCC {mcc_id} for customer {customer_id}"
                        )
                        return mcc_id
        except Exception as e:
            utils.logger.debug(
                f"Probe MCC {mcc_id} for {customer_id} failed: {e}"
            )
            continue

    return None


def _run_search(
    customer_id: str,
    query: str,
    login_customer_id: str | None,
) -> List[Dict[str, Any]]:
    ga_service = utils.get_googleads_service(
        "GoogleAdsService", login_customer_id=login_customer_id
    )
    query_result = ga_service.search_stream(
        customer_id=customer_id, query=query
    )
    final_output: List = []
    for batch in query_result:
        for row in batch.results:
            final_output.append(
                utils.format_output_row(row, batch.field_mask.paths)
            )
    return final_output


def search(
    customer_id: str,
    fields: List[str],
    resource: str,
    conditions: List[str] = None,
    orderings: List[str] = None,
    limit: int | str = None,
    login_customer_id: str = None,
) -> List[Dict[str, Any]]:
    """Fetches data from the Google Ads API using the search method

    Args:
        customer_id: The id of the customer
        fields: The fields to fetch
        resource: The resource to return fields from
        conditions: List of conditions to filter the data, combined using AND clauses
        orderings: How the data is ordered
        limit: The maximum number of rows to return
        login_customer_id: Optional MCC (manager) id to use as the
            `login-customer-id` header. Required when querying a client
            account through its manager. If omitted and the direct call is
            denied, the server attempts to auto-discover the parent MCC
            among the caller's accessible customers.

    """

    query_parts = [f"SELECT {','.join(fields)} FROM {resource}"]

    if conditions:
        query_parts.append(f" WHERE {' AND '.join(conditions)}")

    if orderings:
        query_parts.append(f" ORDER BY {','.join(orderings)}")

    if limit:
        query_parts.append(f" LIMIT {limit}")

    query = "".join(query_parts)
    utils.logger.info(
        f"ads_mcp.search query (customer_id={customer_id}, "
        f"login_customer_id={login_customer_id}) {query}"
    )

    try:
        return _run_search(customer_id, query, login_customer_id)
    except GoogleAdsException as exc:
        if login_customer_id or not _is_user_permission_denied(exc):
            raise
        utils.logger.info(
            f"Permission denied for customer {customer_id}; "
            "attempting to auto-discover parent MCC."
        )
        parent = _discover_parent_mcc(customer_id)
        if not parent:
            raise
        return _run_search(customer_id, query, parent)


_SEARCH_TOOL_DESCRIPTION = f"""
{search.__doc__}

### Hints
    Language Grammar: https://developers.google.com/google-ads/api/docs/query/grammar
    All resources and field references: https://developers.google.com/google-ads/api/fields/v21/overview

    For Conversion issues try looking in offline_conversion_upload_conversion_action_summary

### Hint for customer_id
    should be a string of numbers without punctuation
    if presented in the form 123-456-7890 remove the hyphens and use 1234567890

### Hint for login_customer_id (MCC / manager accounts)
    When querying a client account that is managed by an MCC (manager),
    pass the MCC id as `login_customer_id`. Both ids should be plain digit
    strings without hyphens. If you omit it for a managed client, the
    server will try to auto-discover the parent MCC from the caller's
    accessible customers, but passing it explicitly is faster and more
    reliable.

### Hints for Dates
    All dates should be in the form YYYY-MM-DD and must include the dashes (-)
    Date literals from the Grammar must NEVER be used
    Date ranges should be finite and must include a start and end date

### Hints for limits
    Requests to resource change_event must specify a LIMIT of less than or equal to 10000

### Hints for conversions questions
    https://developers.google.com/google-ads/api/docs/conversions/upload-summaries

### Available resources
    There are 200+ resources available. The most commonly used are:
    campaign, ad_group, ad_group_ad, ad_group_criterion, customer, campaign_budget,
    keyword_view, search_term_view, campaign_criterion, conversion_action, asset,
    asset_group, ad_group_ad_label, campaign_label, click_view, landing_page_view,
    change_event, bidding_strategy, ad_group_label, shopping_performance_view

    Use the `get_resource_fields` tool to look up selectable, filterable, and sortable fields for any resource.
    Use the `list_resources` tool to see all available resource names.
    All fields must be prefixed with the resource being searched. Wildcards and partial fields are not allowed.
"""


mcp.add_tool(
    search,
    title="Fetches data from the Google Ads API using the search method",
    description=_SEARCH_TOOL_DESCRIPTION,
)
