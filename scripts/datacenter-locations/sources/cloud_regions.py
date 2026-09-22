"""
Public cloud regions (AWS / Azure / GCP / OCI / IBM Cloud) located in the US.

Hyperscalers don't publish street addresses for these campuses, so these are
hardcoded from each provider's own region-list docs, at metro-level precision
(precision="metro") rather than scraped — there's nothing to scrape; the
"location" a cloud region publishes IS the metro name. Update this list by
hand if a provider announces a new US region.
"""

from __future__ import annotations

REGIONS = [
    # AWS — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RegionsAndAvailabilityZones.html
    ("aws", "us-east-1", "US East (N. Virginia)", "Ashburn", "Virginia", "VA", 39.0438, -77.4874),
    ("aws", "us-east-2", "US East (Ohio)", "Columbus", "Ohio", "OH", 39.9612, -82.9988),
    ("aws", "us-west-1", "US West (N. California)", "San Jose", "California", "CA", 37.3382, -121.8863),
    ("aws", "us-west-2", "US West (Oregon)", "Boardman", "Oregon", "OR", 45.8399, -119.7006),
    ("aws", "us-gov-east-1", "AWS GovCloud (US-East)", "Ashburn", "Virginia", "VA", 39.0438, -77.4874),
    ("aws", "us-gov-west-1", "AWS GovCloud (US-West)", "Boardman", "Oregon", "OR", 45.8399, -119.7006),
    # Azure — https://learn.microsoft.com/en-us/azure/reliability/regions-list
    ("azure", "eastus", "East US", "Boydton", "Virginia", "VA", 36.6676, -78.3875),
    ("azure", "eastus2", "East US 2", "Boydton", "Virginia", "VA", 36.6676, -78.3875),
    ("azure", "centralus", "Central US", "Des Moines", "Iowa", "IA", 41.5868, -93.6250),
    ("azure", "northcentralus", "North Central US", "Chicago", "Illinois", "IL", 41.8781, -87.6298),
    ("azure", "southcentralus", "South Central US", "San Antonio", "Texas", "TX", 29.4241, -98.4936),
    ("azure", "westus", "West US", "San Jose", "California", "CA", 37.3382, -121.8863),
    ("azure", "westus2", "West US 2", "Quincy", "Washington", "WA", 47.2343, -119.8524),
    ("azure", "westus3", "West US 3", "Phoenix", "Arizona", "AZ", 33.4484, -112.0740),
    ("azure", "westcentralus", "West Central US", "Cheyenne", "Wyoming", "WY", 41.1400, -104.8202),
    # Google Cloud — https://cloud.google.com/compute/docs/regions-zones
    ("gcp", "us-central1", "us-central1", "Council Bluffs", "Iowa", "IA", 41.2619, -95.8608),
    ("gcp", "us-east1", "us-east1", "Moncks Corner", "South Carolina", "SC", 33.1960, -80.0138),
    ("gcp", "us-east4", "us-east4", "Ashburn", "Virginia", "VA", 39.0438, -77.4874),
    ("gcp", "us-east5", "us-east5", "Columbus", "Ohio", "OH", 39.9612, -82.9988),
    ("gcp", "us-south1", "us-south1", "Dallas", "Texas", "TX", 32.7767, -96.7970),
    ("gcp", "us-west1", "us-west1", "The Dalles", "Oregon", "OR", 45.5946, -121.1787),
    ("gcp", "us-west2", "us-west2", "Los Angeles", "California", "CA", 34.0522, -118.2437),
    ("gcp", "us-west3", "us-west3", "Salt Lake City", "Utah", "UT", 40.7608, -111.8910),
    ("gcp", "us-west4", "us-west4", "Las Vegas", "Nevada", "NV", 36.1699, -115.1398),
    # Oracle Cloud Infrastructure
    ("oci", "us-ashburn-1", "US East (Ashburn)", "Ashburn", "Virginia", "VA", 39.0438, -77.4874),
    ("oci", "us-phoenix-1", "US West (Phoenix)", "Phoenix", "Arizona", "AZ", 33.4484, -112.0740),
    ("oci", "us-sanjose-1", "US West (San Jose)", "San Jose", "California", "CA", 37.3382, -121.8863),
    ("oci", "us-chicago-1", "US Midwest (Chicago)", "Chicago", "Illinois", "IL", 41.8781, -87.6298),
    # IBM Cloud
    ("ibm", "us-south", "US South (Dallas)", "Dallas", "Texas", "TX", 32.7767, -96.7970),
    ("ibm", "us-east", "US East (Washington DC)", "Sterling", "Virginia", "VA", 39.0062, -77.4286),
]


def fetch() -> list[dict]:
    records = []
    for provider, region_code, region_name, city, state, state_code, lat, lon in REGIONS:
        records.append(
            {
                "source": "cloud_regions",
                "source_id": f"{provider}:{region_code}",
                "name": f"{provider.upper()} {region_name} ({region_code})",
                "operator": provider.upper(),
                "type": "cloud",
                "status": "existing",
                "address": None,
                "city": city,
                "state": state,
                "state_code": state_code,
                "zip": None,
                "country": "US",
                "latitude": lat,
                "longitude": lon,
                "size_mw": None,
                "year_built": None,
                "precision": "metro",
                "url": None,
            }
        )
    return records


if __name__ == "__main__":
    recs = fetch()
    print(f"cloud_regions: {len(recs)} records")
