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

"""Tools for looking up GAQL resource fields on demand."""

import json
from typing import Dict, List, Optional

from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


def _load_gaql_resources() -> List[Dict]:
    """Loads and caches the GAQL resources from disk."""
    try:
        with open(utils.get_gaql_resources_filepath(), "r") as file:
            return json.load(file)
    except FileNotFoundError:
        utils.logger.error("The GAQL resources file was not found.")
        return []


_gaql_resources: Optional[List[Dict]] = None


def _get_gaql_resources() -> List[Dict]:
    global _gaql_resources
    if _gaql_resources is None:
        _gaql_resources = _load_gaql_resources()
    return _gaql_resources


@mcp.tool()
def list_resources() -> List[str]:
    """Returns the names of all available Google Ads API resources that can be used with the search tool.

    Use this to discover resource names, then use get_resource_fields to look up
    the selectable, filterable, and sortable fields for a specific resource.
    Full reference: https://developers.google.com/google-ads/api/fields/v21/overview
    """
    return [r["resource"] for r in _get_gaql_resources()]


@mcp.tool()
def get_resource_fields(resource: str) -> Dict:
    """Returns the selectable, filterable, and sortable fields for a given Google Ads API resource.

    Args:
        resource: The resource name (e.g. "campaign", "ad_group", "ad_group_ad").
                  Use list_resources to see all available names.
    """
    for r in _get_gaql_resources():
        if r["resource"] == resource:
            return r
    return {"error": f"Resource '{resource}' not found. Use list_resources to see available resources."}
