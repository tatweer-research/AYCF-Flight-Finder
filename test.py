import requests

# 🔗 Endpoint URL (specific to your working session)
url = "https://multipass.wizzair.com/de/w6/subscriptions/json/availability/b128d7ef-d1e5-4b7a-aa5e-6e66fc5e4e73"

# 📄 Headers (must include correct X-XSRF-TOKEN)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://multipass.wizzair.com",
    "Referer": "https://multipass.wizzair.com/de/w6/subscriptions/availability/b128d7ef-d1e5-4b7a-aa5e-6e66fc5e4e73",
    "X-XSRF-TOKEN": "eyJpdiI6IjMyek5CSlNTd3MrejM4V25zQ1wvS0JRPT0iLCJ2YWx1ZSI6Iit3YzIzZHZiTXVSN2ZreUtUQ1pnUEZnNEVPdGFjRGU3WEgxaloyYVd5eEZ3VWZPNzRHTHYwNTRpaXhOZ3d0Mjc3clwvZUZVYktDU3V5VTJWNjlVOEVDUT09IiwibWFjIjoiM2E5NWM2MWZiNDc1YjNmMGY5ZWM5NzA1OWNiMzhlMDNjZjJiYTJhNDQ1ZTEwODBlYWJlMzI0NTIxZTg5MTA5ZCJ9"
}

cookies = {
    "XSRF-TOKEN": "eyJpdiI6IjMyek5CSlNTd3MrejM4V25zQ1wvS0JRPT0iLCJ2YWx1ZSI6Iit3YzIzZHZiTXVSN2ZreUtUQ1pnUEZnNEVPdGFjRGU3WEgxaloyYVd5eEZ3VWZPNzRHTHYwNTRpaXhOZ3d0Mjc3clwvZUZVYktDU3V5VTJWNjlVOEVDUT09IiwibWFjIjoiM2E5NWM2MWZiNDc1YjNmMGY5ZWM5NzA1OWNiMzhlMDNjZjJiYTJhNDQ1ZTEwODBlYWJlMzI0NTIxZTg5MTA5ZCJ9",
    "laravel_session": "eyJpdiI6InNKTVp0MFozZ1ArY1wvMG93MnBwb0VRPT0iLCJ2YWx1ZSI6InA3TVwvb25VcjR3NFVtbHlzcjZcL1FhbEVXbXFRZTRSV2VheldyM1pvZ2V5RVwvNUVMTGcxQmd5WWNRUHhXYXJqYThJT0xDUzhjZXBGWUZCRzVTWW01MWh3PT0iLCJtYWMiOiJhZjNiM2ZiMDNmY2FmMjI3OGQ1YjhjYzRkNjkxM2VkZDljYjE1OTE4MDYzNGU3NmEyMmM0MWZkOWU3OWU1M2JhIn0="
}

# ✈️ Payload with your tested search parameters
payload = {
    "flightType": "OW",
    "origin": "AUH",
    "destination": "AMM",
    "departure": "2025-04-13",
    "arrival": None,
    "intervalSubtype": None
}

# 📡 POST request
response = requests.post(url, headers=headers, cookies=cookies, json=payload)

# 🧾 Handle response
if response.status_code == 200:
    data = response.json()
    print("✅ Flights found:")
    for flight in data.get("flightsOutbound", []):
        print(f"- {flight['flightCode']} from {flight['departureStationText']} to {flight['arrivalStationText']}")
        print(f"  Departure: {flight['departure']} ({flight['departureDate']})")
        print(f"  Arrival:   {flight['arrival']} ({flight['arrivalDate']})")
        print(f"  Price:     {flight['price']} {flight['currency']} (Total: {flight['totalPrice']} {flight['currency']})\n")
else:
    print("❌ Request failed:", response.status_code)
    print(response.text)
