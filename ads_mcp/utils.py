#!/usr/bin/env python

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

"""Common utilities used by the MCP server."""

from functools import lru_cache
from typing import Any
import proto
import logging
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.v21.services.services.google_ads_service import (
    GoogleAdsServiceClient,
)

from google.ads.googleads.util import get_nested_attr
import google.auth
from ads_mcp.mcp_header_interceptor import MCPHeaderInterceptor
import os
import importlib.resources

# filename for generated field information used by search
_GAQL_FILENAME = "gaql_resources.json"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Read-only scope for Analytics Admin API and Analytics Data API.
_READ_ONLY_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"


def _create_credentials() -> google.auth.credentials.Credentials:
    """Returns Application Default Credentials with read-only scope."""
    (credentials, _) = google.auth.default(scopes=[_READ_ONLY_ADS_SCOPE])
    return credentials


def _get_developer_token() -> str:
    """Returns the developer token from the environment variable GOOGLE_ADS_DEVELOPER_TOKEN."""
    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    if dev_token is None:
        raise ValueError(
            "GOOGLE_ADS_DEVELOPER_TOKEN environment variable not set."
        )
    return dev_token


def _get_login_customer_id() -> str:
    """Returns login customer id, if set, from the environment variable GOOGLE_ADS_LOGIN_CUSTOMER_ID."""
    return os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")


def _normalize_customer_id(customer_id: str | None) -> str | None:
    """Normalizes customer ids so callers can pass values with or without dashes."""
    if customer_id is None:
        return None
    normalized = str(customer_id).replace("-", "").strip()
    return normalized or None


@lru_cache(maxsize=32)
def get_googleads_client(
    login_customer_id: str | None = None,
) -> GoogleAdsClient:
    """Returns a Google Ads client, optionally scoped to a manager account."""
    # Use this line if you have a google-ads.yaml file
    # client = GoogleAdsClient.load_from_storage()
    resolved_login_customer_id = _normalize_customer_id(
        login_customer_id or _get_login_customer_id()
    )
    client = GoogleAdsClient(
        credentials=_create_credentials(),
        developer_token=_get_developer_token(),
        login_customer_id=resolved_login_customer_id,
    )

    return client


def get_googleads_service(
    serviceName: str, login_customer_id: str | None = None
) -> GoogleAdsServiceClient:
    return get_googleads_client(login_customer_id).get_service(
        serviceName, interceptors=[MCPHeaderInterceptor()]
    )


def get_googleads_type(typeName: str, login_customer_id: str | None = None):
    return get_googleads_client(login_customer_id).get_type(typeName)


def format_output_value(value: Any) -> Any:
    if isinstance(value, proto.Enum):
        return value.name
    else:
        return value


def _resolve_proto_attr(row: proto.Message, attr: str) -> Any:
    """Resolve a GAQL field path on a proto-plus row.

    proto-plus renames fields that clash with Python built-ins by appending an
    underscore (e.g. ``type`` → ``type_``).  The field mask returned by the API
    uses the original proto name, so we try the original first and fall back to
    the suffixed variant.
    """
    try:
        return get_nested_attr(row, attr)
    except AttributeError:
        # Try the proto-plus escaped name: split on '.', append '_' to the
        # last segment, and retry.
        parts = attr.split(".")
        parts[-1] = parts[-1] + "_"
        return get_nested_attr(row, ".".join(parts))


def format_output_row(row: proto.Message, attributes):
    return {
        attr: format_output_value(_resolve_proto_attr(row, attr))
        for attr in attributes
    }


def get_gaql_resources_filepath():
    package_root = importlib.resources.files("ads_mcp")
    file_path = package_root.joinpath(_GAQL_FILENAME)
    return file_path
