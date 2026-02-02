"""Test all auth methods from precisemcp against CallListData endpoint."""
import asyncio
import httpx
import json
import time
import sys

# Credentials from precisemcp
PARTNER_API_KEY = "f0M65v8av8ns3iZ4XFEacXc1dKWqWI6756Nb4nRVymYysN1jtKmSBQUyEfgGeRc3tDyBF5bP61Z8VcT4zm8GvCe8xSiLgS143V6Y3OQ4a062qutS13qgx55T4A9DNhAk"
CHATBOT_PARTNER_API_KEY = "f0M65v8av8ns3iZ4XFEacXc1dKWqWI6756Nb4nRVymYysN1jDyBF5bP61Z8iLgS143V6Y3OQ4a062qutS13qgx55T4A9DNhAk"
CHATBOT_API_USER = "Chatbot"
CHATBOT_API_PASSWORD = "lcNvSuG3pXDb0rht6Vwh0rhDpXCCzCzCzWe4L3GjQsGHpXiz0rxZ6V4s9K8W5eLcv"

TOKEN_ENDPOINTS = {
    "staging_patientportal": "https://staging-app.radflow360.com/patientportalapi/Partner/GetRefreshToken",
    "prod_patientportal": "https://app.radflow360.com/patientportalapi/Partner/GetRefreshToken",
    "pbx": "https://app.radflow360.com/pbxcallAPI/Partner/GetRefreshToken",
    "chatbot": "https://app.radflow360.com/chatbotapi/Partner/GetRefreshToken",
}

TARGET_URL = "https://app.radflow360.com/chatbotapi/Patient/CallListData?patientId=PRE1068792"

results = []

def log(msg):
    results.append(msg)
    print(msg)

async def get_jwt(client, name, token_url, api_key):
    """Fetch JWT from a token endpoint."""
    url = f"{token_url}?partnerApiKey={api_key}"
    try:
        resp = await client.post(url, headers={"Accept": "application/json"}, data="", timeout=30.0)
        if resp.status_code != 200:
            return None, f"Token endpoint returned {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        result = data.get("result", {})
        token = result.get("jwtToken", "") if isinstance(result, dict) else result
        if token:
            return token, None
        return None, f"No jwtToken in response: {json.dumps(data)[:300]}"
    except Exception as e:
        return None, str(e)

async def test_bearer(client, label, token):
    """Test CallListData with Bearer token."""
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        resp = await client.get(TARGET_URL, headers=headers, timeout=60.0)
        body = resp.text[:2000] if resp.text else "(empty)"
        return resp.status_code, body
    except Exception as e:
        return None, str(e)

async def main():
    log("=" * 80)
    log(f"CallListData Auth Test — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Target: {TARGET_URL}")
    log("=" * 80)

    async with httpx.AsyncClient(verify=False) as client:

        # ---- METHOD 1: No auth ----
        log("\n" + "=" * 80)
        log("METHOD 1: No Authentication (plain GET)")
        log("=" * 80)
        try:
            resp = await client.get(TARGET_URL, headers={"Accept": "application/json"}, timeout=60.0)
            log(f"Status: {resp.status_code}")
            log(f"Response Headers: {dict(resp.headers)}")
            log(f"Body: {resp.text[:2000] if resp.text else '(empty)'}")
        except Exception as e:
            log(f"Error: {e}")

        # ---- METHOD 2: Basic Auth (Chatbot user/pass) ----
        log("\n" + "=" * 80)
        log("METHOD 2: Basic Auth (CHATBOT_API_USER / CHATBOT_API_PASSWORD)")
        log("=" * 80)
        try:
            resp = await client.get(
                TARGET_URL,
                headers={"Accept": "application/json"},
                auth=(CHATBOT_API_USER, CHATBOT_API_PASSWORD),
                timeout=60.0,
            )
            log(f"Status: {resp.status_code}")
            log(f"Response Headers: {dict(resp.headers)}")
            log(f"Body: {resp.text[:2000] if resp.text else '(empty)'}")
        except Exception as e:
            log(f"Error: {e}")

        # ---- METHOD 3: API Key as query param (PARTNER_API_KEY) ----
        log("\n" + "=" * 80)
        log("METHOD 3: API Key as query param (partnerApiKey=PARTNER_API_KEY)")
        log("=" * 80)
        try:
            url_with_key = f"{TARGET_URL}&partnerApiKey={PARTNER_API_KEY}"
            resp = await client.get(url_with_key, headers={"Accept": "application/json"}, timeout=60.0)
            log(f"Status: {resp.status_code}")
            log(f"Response Headers: {dict(resp.headers)}")
            log(f"Body: {resp.text[:2000] if resp.text else '(empty)'}")
        except Exception as e:
            log(f"Error: {e}")

        # ---- METHOD 4: API Key as query param (CHATBOT_PARTNER_API_KEY) ----
        log("\n" + "=" * 80)
        log("METHOD 4: API Key as query param (partnerApiKey=CHATBOT_PARTNER_API_KEY)")
        log("=" * 80)
        try:
            url_with_key = f"{TARGET_URL}&partnerApiKey={CHATBOT_PARTNER_API_KEY}"
            resp = await client.get(url_with_key, headers={"Accept": "application/json"}, timeout=60.0)
            log(f"Status: {resp.status_code}")
            log(f"Response Headers: {dict(resp.headers)}")
            log(f"Body: {resp.text[:2000] if resp.text else '(empty)'}")
        except Exception as e:
            log(f"Error: {e}")

        # ---- METHODS 5-8: Bearer JWT from each token endpoint with PARTNER_API_KEY ----
        for name, token_url in TOKEN_ENDPOINTS.items():
            log("\n" + "=" * 80)
            log(f"METHOD: Bearer JWT from [{name}] with PARTNER_API_KEY")
            log(f"Token URL: {token_url}")
            log("=" * 80)
            token, err = await get_jwt(client, name, token_url, PARTNER_API_KEY)
            if err:
                log(f"Token fetch failed: {err}")
                continue
            log(f"Got JWT (len={len(token)})")
            status, body = await test_bearer(client, name, token)
            log(f"Status: {status}")
            log(f"Body: {body}")

        # ---- METHODS 9-12: Bearer JWT from each token endpoint with CHATBOT_PARTNER_API_KEY ----
        for name, token_url in TOKEN_ENDPOINTS.items():
            log("\n" + "=" * 80)
            log(f"METHOD: Bearer JWT from [{name}] with CHATBOT_PARTNER_API_KEY")
            log(f"Token URL: {token_url}")
            log("=" * 80)
            token, err = await get_jwt(client, name, token_url, CHATBOT_PARTNER_API_KEY)
            if err:
                log(f"Token fetch failed: {err}")
                continue
            log(f"Got JWT (len={len(token)})")
            status, body = await test_bearer(client, name, token)
            log(f"Status: {status}")
            log(f"Body: {body}")

        # ---- METHOD 13: Basic Auth + Bearer JWT combined ----
        log("\n" + "=" * 80)
        log("METHOD: Basic Auth + Chatbot Bearer JWT combined")
        log("=" * 80)
        token, err = await get_jwt(client, "chatbot", TOKEN_ENDPOINTS["chatbot"], CHATBOT_PARTNER_API_KEY)
        if err:
            log(f"Token fetch failed: {err}")
        else:
            log(f"Got JWT (len={len(token)})")
            try:
                resp = await client.get(
                    TARGET_URL,
                    headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                    auth=(CHATBOT_API_USER, CHATBOT_API_PASSWORD),
                    timeout=60.0,
                )
                log(f"Status: {resp.status_code}")
                log(f"Body: {resp.text[:2000] if resp.text else '(empty)'}")
            except Exception as e:
                log(f"Error: {e}")

        # ---- METHOD 14: API Key as header ----
        log("\n" + "=" * 80)
        log("METHOD: API Key as X-Api-Key header (PARTNER_API_KEY)")
        log("=" * 80)
        try:
            resp = await client.get(
                TARGET_URL,
                headers={"Accept": "application/json", "X-Api-Key": PARTNER_API_KEY},
                timeout=60.0,
            )
            log(f"Status: {resp.status_code}")
            log(f"Body: {resp.text[:2000] if resp.text else '(empty)'}")
        except Exception as e:
            log(f"Error: {e}")

        # ---- METHOD 15: API Key as header (chatbot key) ----
        log("\n" + "=" * 80)
        log("METHOD: API Key as X-Api-Key header (CHATBOT_PARTNER_API_KEY)")
        log("=" * 80)
        try:
            resp = await client.get(
                TARGET_URL,
                headers={"Accept": "application/json", "X-Api-Key": CHATBOT_PARTNER_API_KEY},
                timeout=60.0,
            )
            log(f"Status: {resp.status_code}")
            log(f"Body: {resp.text[:2000] if resp.text else '(empty)'}")
        except Exception as e:
            log(f"Error: {e}")

    # Write results file
    outpath = "/home/fret/work/OutboundVoiceAI/calllistdata_auth_results.txt"
    with open(outpath, "w") as f:
        f.write("\n".join(results))
    log(f"\nResults written to {outpath}")

asyncio.run(main())
