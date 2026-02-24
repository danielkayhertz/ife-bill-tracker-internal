#!/usr/bin/env python3
"""Update bill status from ILGA.gov FTP XML files.

Run from ife-bill-tracker/ directory:
    python scripts/update_bill_status.py

Or from anywhere — the script uses __file__ to find the repo root.
"""

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ILGA_FTP_BASE = "https://www.ilga.gov/ftp/legislation/104/BillStatus/XML/10400"

# All 25 bills — mirrors legislationData in index.html
BILLS = [
    # 2025 Session — Endorsed
    {"id": 1, "billNumber": "HB3466", "title": "Affordable Housing Special Assessment Program (AHSAP)", "description": "Amends property tax code. Clarifies needed property improvements to remain in special assessment program, allows property to remain in program even if county opts out. Details IHDA's responsibility in calculating/sharing minimum per sq. ft. expenditure requirements for rehabilitation to qualify. Extends AHSAP to 2037.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Property Taxes", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3466&DocTypeID=HB&LegId=162109&SessionID=114"},
    {"id": 2, "billNumber": "SB1911", "title": "Affordable Housing Special Assessment Program (Senate)", "description": "Senate companion to HB3466. Amends property tax code. Clarifies needed property improvements to remain in special assessment program, allows property to remain in program even if county opts out. Extends AHSAP to 2037. Governor approved 12/12/25.", "year": [2025], "status": "Passed into law", "type": "Endorsed", "category": "Property Taxes", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1911&DocTypeID=SB&LegId=161199&SessionID=114"},
    {"id": 3, "billNumber": "SB0062", "title": "Build Illinois Homes Tax Credit Act", "description": "Creates the Build Illinois Homes Tax Credit Act. Qualified developments are low-income housing projects. Upon construction or rehabilitation, IHDA or DOH issues state credit eligibility statements. Allows qualified taxpayers to be awarded tax credits for their development if necessary for financial feasibility. Would create a state match to the federal Low Income Housing Tax Credit.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Affordable Housing Development", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=62&DocTypeID=SB&LegId=157167&SessionID=114"},
    {"id": 4, "billNumber": "HB2545", "title": "AHPAA Supportive Housing Amendment", "description": "Amends Affordable Housing Planning and Appeals Act. Allows for a broader range of parties to appeal decisions and clarifies timeline for appeals and responses, consequences of failing to respond, and the municipality's burden in responding. Shifts burden of proof onto municipality to demonstrate that a proposed supportive housing project would be detrimental.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "AHPAA", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=2545&DocTypeID=HB&LegId=160392&SessionID=114"},
    {"id": 5, "billNumber": "HB1814", "title": "Missing Middle Housing Act", "description": "Amends zoning division of IL Municipal Code. Requires large cities to allow middle housing development on large lots zoned residential. Requires smaller cities to allow development of at least duplexes on lots allowing detached single family dwellings. Prohibits applicable municipalities from discouraging development or regulating development in an inconsistent manner.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1814&DocTypeID=HB&LegId=159270&SessionID=114"},
    {"id": 6, "billNumber": "HB1813", "title": "ADU Authorization Act", "description": "Amends the Control Over Building and Construction Article of the IL Municipal Code. Defines accessory dwelling unit and efficiency unit. Prohibits municipalities from prohibiting the building or use of ADUs and prohibits home rule units from acting inconsistently with the Act.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1813&DocTypeID=HB&LegId=159269&SessionID=114"},
    {"id": 7, "billNumber": "HB3552", "title": "Local Accessory Dwelling Unit Act", "description": "Creates Local Accessory Dwelling Unit Act. Defines accessory dwelling unit, types of units, and discretionary review. Prohibits local governments from prohibiting the building or use of ADUs and sets requirements for ADU application review, timelines, delays, and processing. Prohibits home rule units from acting inconsistently with the Act.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3552&DocTypeID=HB&LegId=162242&SessionID=114"},
    {"id": 8, "billNumber": "HB1843", "title": "Family Status Housing Protection Act", "description": "Amends the Zoning Division of the IL Municipal Code. Disallows classification, regulation, and restriction on use of property based on family relationship. Prohibits municipalities from adopting zoning regulations that prohibit 2 or more unrelated people from living together, and regulations that prohibit community-integrated living arrangements.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1843&DocTypeID=HB&LegId=159333&SessionID=114"},
    {"id": 9, "billNumber": "HB3288", "title": "Affordable Communities Act", "description": "Creates the Affordable Communities Act. Clarifies and defines middle housing types. Applies to zoning units with populations over 100,000 and prohibits regulations from preventing middle housing development. Requires these zoning units to adopt land use ordinances and amend zoning maps/ordinances to implement middle housing requirements. Allows IHDA to adopt emergency rules for implementing the Act's requirements.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3288&DocTypeID=HB&LegId=161778&SessionID=114"},
    {"id": 10, "billNumber": "HB1429", "title": "Bill of Rights for the Homeless Act Amendment", "description": "Amends the Bill of Rights for the Homeless Act. Prohibits state and local government from passing rules that fine or criminally penalize people experiencing unsheltered homelessness for engaging in life-sustaining activities (like eating, keeping belongings, and sleeping) on public property. Requires written and oral notice to be given prior to removal at a site. Makes unsheltered homelessness an affirmative defense to charges of violating rules that criminalize occupying or engaging in life-sustaining activities.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Housing", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1429&DocTypeID=HB&LegId=157430&SessionID=114"},
    {"id": 11, "billNumber": "SB2264", "title": "Crime-Free and Nuisance Housing Ordinances Regulation", "description": "Amends the Counties Code, IL Municipal Code, and Housing Authorities Act. Prohibits counties, municipalities, and housing authorities from adopting, enforcing, or implementing regulations affecting a tenancy because of contact with law enforcement or emergency services. Eliminates unfair penalties and evictions of tenants based on alleged criminal or nuisance activity.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Tenant Protections", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=2264&DocTypeID=SB&LegId=162041&SessionID=114"},
    {"id": 12, "billNumber": "HB3256", "title": "People Over Parking Act", "description": "Creates the People Over Parking Act. Defines various development projects and parking requirements. Prohibits minimum automobile parking requirements if a project is within 1/2 mile of a public transportation hub. Allows local governments to impose requirements for parking spaces if a project provides parking voluntarily. Prohibits home rule units from acting inconsistently.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3256&DocTypeID=HB&LegId=161742&SessionID=114"},
    {"id": 13, "billNumber": "SB2352", "title": "People Over Parking Act (Senate)", "description": "Senate companion to HB3256. Creates the People Over Parking Act. Prohibits minimum automobile parking requirements if a project is within 1/2 mile of a public transportation hub.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=2352&DocTypeID=SB&LegId=162316&SessionID=114"},
    {"id": 14, "billNumber": "SB2111", "title": "Vehicle Code - Bicycles Exemptions", "description": "Amends the IL Vehicle Code. People riding a bike on the road are not prohibited from side-by-side riding, riding contraflow on one-way streets, and rolling through stop signs at clear intersections. Governor approved 12/16/25.", "year": [2025], "status": "Passed into law", "type": "Endorsed", "category": "Transportation", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=2111&DocTypeID=SB&LegId=161644&SessionID=114"},
    {"id": 15, "billNumber": "HB3438", "title": "Transportation Reform Bill", "description": "Amends DOT Law of the Civil Admin Code of IL. Amends the Regional Transportation Authority Act, creates the Northern IL Transit Authority, generally acts as the transit reform bill with funding. Includes the People Over Parking Act provisions.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Transportation", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3438&DocTypeID=HB&LegId=162067&SessionID=114"},
    # 2026 Session — New Bills
    {"id": 16, "billNumber": "HB4377", "title": "PHA - No Work Requirements", "description": "Amends Housing Authorities Act. Unless otherwise required by federal law or regulation, prohibits housing authorities from establishing time limits and work requirements as conditions of eligibility for rent subsidy or assistance. Housing authorities may encourage participation in voluntary employment or job training if it does not impact eligibility.", "year": [2026], "status": "Not passed into law", "type": "Sponsored", "category": "Public Housing", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4377&GAID=18&DocTypeID=HB&LegId=164950&SessionID=114"},
    {"id": 17, "billNumber": "SB3084", "title": "PHA - No Work Requirements (Senate)", "description": "Senate companion to HB4377. Amends Housing Authorities Act. Unless otherwise required by federal law or regulation, prohibits housing authorities from establishing time limits and work requirements as conditions of eligibility for rent subsidy or assistance.", "year": [2026], "status": "Not passed into law", "type": "Sponsored", "category": "Public Housing", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3084&GAID=18&DocTypeID=SB&LegId=165665&SessionID=114"},
    {"id": 18, "billNumber": "HB4413", "title": "Revenue - Affordable Housing", "description": "Amends IL Housing Dev. Act and IL Income Tax Act. Credits awarded under affordable housing tax donation program is limited in 2027 and will increase by 10% each year after. Affordable housing donation income tax credit applies through taxable year ending 2036.", "year": [2026], "status": "Not passed into law", "type": "Endorsed", "category": "Affordable Housing Development", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4413&GAID=18&DocTypeID=HB&LegId=165058&SessionID=114"},
    {"id": 19, "billNumber": "SB3169", "title": "Revenue - Affordable Housing (CLT)", "description": "Amends Hotel Operators' Occupation Tax Act. Imposes a tax upon hosting platforms that facilitate renting, leasing, or letting of short-term rentals. Proceeds shall be deposited in the Community Land Trust Fund. Property owned by a nonprofit community land trust used exclusively for creation and maintenance of permanently affordable residences is exempt from property tax.", "year": [2026], "status": "Not passed into law", "type": "Endorsed", "category": "Affordable Housing Development", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3169&GAID=18&DocTypeID=SB&LegId=165814&SessionID=114"},
    {"id": 20, "billNumber": "HB4510", "title": "Missing Middle Housing Affordability Act", "description": "Creates the Missing Middle Housing Affordability Act.", "year": [2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4510&GAID=18&DocTypeID=HB&LegId=165295&SessionID=114"},
    {"id": 21, "billNumber": "HB4568", "title": "Home Illinois Program ($352M)", "description": "Appropriates $352,200,000 from the General Revenue Fund to DHS for grants and administrative expenses of the Home Illinois Program, including pilot programs to prevent and end homelessness, including homelessness prevention, emergency and transitional housing, rapid rehousing, outreach, and related services and supports.", "year": [2026], "status": "Not passed into law", "type": "Endorsed", "category": "Housing", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4568&GAID=18&DocTypeID=HB&LegId=165428&SessionID=114"},
    {"id": 22, "billNumber": "SB2969", "title": "Home Illinois Program (Senate)", "description": "Senate companion to HB4568. Appropriates $352,200,000 from the General Revenue Fund to DHS for grants and administrative expenses of the Home Illinois Program to prevent and end homelessness.", "year": [2026], "status": "Not passed into law", "type": "Endorsed", "category": "Housing", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2969&GAID=18&DocTypeID=SB&LegId=165401&SessionID=114"},
    {"id": 23, "billNumber": "SB3165", "title": "Housing is Recovery Program ($10M)", "description": "Appropriates $10,000,000 from the General Revenue Fund to DHS for the Housing is Recovery Program to support rental assistance for individuals with mental health and substance use challenges who are experiencing homelessness.", "year": [2026], "status": "Not passed into law", "type": "Endorsed", "category": "Housing", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3165&GAID=18&DocTypeID=SB&LegId=165810&SessionID=114"},
    {"id": 24, "billNumber": "HB4588", "title": "Parking - High Population Cities", "description": "Amends the People Over Parking Act. Provides that the Act applies to municipalities with a population of more than 2 million, rather than all units of local government. Would weaken the People Over Parking Act by limiting its scope.", "year": [2026], "status": "Not passed into law", "type": "Opposed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4588&GAID=18&DocTypeID=HB&LegId=165448&SessionID=114"},
    {"id": 25, "billNumber": "SB3009", "title": "Neighborhood Housing ($5M)", "description": "Appropriates $5,000,000 from the General Revenue Fund to the Department of Commerce and Economic Opportunity for a grant to Neighborhood Housing Services of Chicago for costs associated with funding equitable mortgage lending and homebuyer subsidies, foreclosure prevention services, and other support.", "year": [2026], "status": "Not passed into law", "type": "Endorsed", "category": "Housing", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3009&GAID=18&DocTypeID=SB&LegId=165513&SessionID=114"},
]


def parse_bill_number(bill_number):
    """Parse 'HB3466' → ('HB', '3466'), 'SB0062' → ('SB', '0062')."""
    m = re.match(r'^([A-Z]+)(\d+)$', bill_number)
    if not m:
        raise ValueError(f"Cannot parse bill number: {bill_number}")
    return m.group(1), m.group(2)


def get_xml_url(bill_number):
    """Build ILGA FTP XML URL. DocNum is zero-padded to 4 digits."""
    doc_type, doc_num = parse_bill_number(bill_number)
    padded = doc_num.zfill(4)
    return f"{ILGA_FTP_BASE}{doc_type}{padded}.xml"


def fetch_xml(url):
    """Fetch URL; return bytes or None on error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IFE-BillTracker/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except Exception as e:
        print(f"    WARNING: fetch failed for {url}: {e}", file=sys.stderr)
        return None


def get_last_action_fields(root):
    """Extract lastAction text and date from <lastaction><action>/<statusdate> structure.

    ILGA XML structure:
      <lastaction>
        <statusdate>3/21/2025</statusdate>
        <chamber>House</chamber>
        <action>Rule 19(a) / Re-referred to Rules Committee</action>
      </lastaction>
    """
    la_el = root.find("lastaction")
    if la_el is None:
        return "", ""
    action_el = la_el.find("action")
    date_el = la_el.find("statusdate")
    last_action = (action_el.text or "").strip() if action_el is not None else ""
    last_action_date = (date_el.text or "").strip() if date_el is not None else ""
    return last_action, last_action_date


def get_action_texts(root):
    """Collect all <action> texts from the flat children of <actions>.

    ILGA XML structure (flat siblings, not nested):
      <actions>
        <statusdate>...</statusdate><chamber>House</chamber><action>Filed...</action>
        <statusdate>...</statusdate><chamber>House</chamber><action>First Reading</action>
        ...
      </actions>
    """
    texts = []
    actions_el = root.find("actions")
    if actions_el is not None:
        for child in actions_el:
            if child.tag.lower() == "action" and child.text:
                texts.append(child.text.strip().lower())
    return texts


def map_stage(last_action, action_history, doc_type):
    """Map last action + action history to a stage label."""
    la = last_action.lower()

    # Final-outcome stages — check first
    if "approved by governor" in la or "public act" in la:
        return "Signed into Law"
    if "sent to the governor" in la or "to the governor" in la:
        return "Awaiting Governor Signature"
    if "passed both" in la or "enrolled" in la:
        return "Enrolled"
    if "passed senate" in la:
        return "Passed Senate"
    if "passed house" in la:
        return "Passed House"
    if any(k in la for k in ["vetoed", "failed", "did not pass", "tabled", "withdrawn"]):
        return "Failed"

    # Chamber inference for committee-phase activity.
    # ILGA uses "Arrive in Senate" / "Arrive in House" for chamber crossings
    # (not "Passed House" / "Passed Senate", which are the lastaction final-outcome phrases).
    history = " ".join(action_history)
    if "passed house" in history or "arrive in senate" in history:
        # Bill has crossed to the Senate
        return "In Senate Committee"
    elif "passed senate" in history or "arrive in house" in history:
        # Bill has crossed to the House
        return "In House Committee"
    else:
        # Still in originating chamber
        return "In House Committee" if doc_type == "HB" else "In Senate Committee"


def process_bill(bill, prev_data):
    """Fetch ILGA XML and return updated bill dict. Falls back to previous data on error."""
    bill_number = bill["billNumber"]
    doc_type, _ = parse_bill_number(bill_number)
    url = get_xml_url(bill_number)
    print(f"  {bill_number} -> {url}")

    xml_bytes = fetch_xml(url)
    if xml_bytes is None:
        prev = prev_data.get(bill_number, {})
        return {
            **bill,
            "stage": prev.get("stage", "Unknown"),
            "lastAction": prev.get("lastAction", ""),
            "lastActionDate": prev.get("lastActionDate", ""),
            "ilgaFetchedAt": prev.get("ilgaFetchedAt", ""),
        }

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"    WARNING: XML parse error for {bill_number}: {e}", file=sys.stderr)
        prev = prev_data.get(bill_number, {})
        return {
            **bill,
            "stage": prev.get("stage", "Unknown"),
            "lastAction": prev.get("lastAction", ""),
            "lastActionDate": prev.get("lastActionDate", ""),
            "ilgaFetchedAt": prev.get("ilgaFetchedAt", ""),
        }

    last_action, last_action_date = get_last_action_fields(root)
    action_history = get_action_texts(root)

    stage = map_stage(last_action, action_history, doc_type)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"    stage={stage}  lastAction={last_action[:70]}")

    return {
        **bill,
        "stage": stage,
        "lastAction": last_action,
        "lastActionDate": last_action_date,
        "ilgaFetchedAt": fetched_at,
    }


def load_previous_data(output_path):
    """Load previous bills.json to preserve data on individual fetch failures."""
    if not output_path.exists():
        return {}
    try:
        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)
        return {b["billNumber"]: b for b in data}
    except Exception:
        return {}


def main():
    repo_root = Path(__file__).parent.parent
    output_path = repo_root / "data" / "bills.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prev_data = load_previous_data(output_path)
    print(f"Updating {len(BILLS)} bills -> {output_path}\n")

    results = []
    changed = 0

    for bill in BILLS:
        result = process_bill(bill, prev_data)
        results.append(result)
        prev = prev_data.get(bill["billNumber"], {})
        if result.get("stage") != prev.get("stage") or result.get("lastAction") != prev.get("lastAction"):
            changed += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone. {changed} bill(s) changed. Written to {output_path}")


if __name__ == "__main__":
    main()
