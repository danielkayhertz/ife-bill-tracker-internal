#!/usr/bin/env python3
"""Update bill status from ILGA.gov FTP XML files.

Run from ife-bill-tracker-internal/ directory:
    python scripts/update_bill_status.py

Or from anywhere — the script uses __file__ to find the repo root.

Internal version adds:
  - stageChangedAt tracking (set when stage label changes vs. previous run)
  - nextActionDate / nextActionType (parsed from ILGA XML <nextaction> element)
  - user-bills.json refresh (updates ILGA fields while preserving user-set fields)
"""

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ILGA_FTP_BASE = "https://www.ilga.gov/ftp/legislation/104/BillStatus/XML/10400"

# All 25 base bills — mirrors FALLBACK_DATA in index.html
BILLS = [
    # 2025 Session — Endorsed
    {"id": 1,  "billNumber": "HB3466", "title": "Affordable Housing Special Assessment Program (AHSAP)", "description": "Amends property tax code. Clarifies needed property improvements to remain in special assessment program, allows property to remain in program even if county opts out. Details IHDA's responsibility in calculating/sharing minimum per sq. ft. expenditure requirements for rehabilitation to qualify. Extends AHSAP to 2037.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Property Taxes", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3466&DocTypeID=HB&LegId=162109&SessionID=114"},
    {"id": 2,  "billNumber": "SB1911", "title": "Affordable Housing Special Assessment Program (Senate)", "description": "Senate companion to HB3466. Amends property tax code. Clarifies needed property improvements to remain in special assessment program, allows property to remain in program even if county opts out. Extends AHSAP to 2037. Governor approved 12/12/25.", "year": [2025], "status": "Passed into law", "type": "Endorsed", "category": "Property Taxes", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1911&DocTypeID=SB&LegId=161199&SessionID=114"},
    {"id": 3,  "billNumber": "SB0062", "title": "Build Illinois Homes Tax Credit Act", "description": "Creates the Build Illinois Homes Tax Credit Act. Qualified developments are low-income housing projects. Upon construction or rehabilitation, IHDA or DOH issues state credit eligibility statements. Allows qualified taxpayers to be awarded tax credits for their development if necessary for financial feasibility. Would create a state match to the federal Low Income Housing Tax Credit.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Affordable Housing Development", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=62&DocTypeID=SB&LegId=157167&SessionID=114"},
    {"id": 4,  "billNumber": "HB2545", "title": "AHPAA Supportive Housing Amendment", "description": "Amends Affordable Housing Planning and Appeals Act. Allows for a broader range of parties to appeal decisions and clarifies timeline for appeals and responses, consequences of failing to respond, and the municipality's burden in responding. Shifts burden of proof onto municipality to demonstrate that a proposed supportive housing project would be detrimental.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "AHPAA", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=2545&DocTypeID=HB&LegId=160392&SessionID=114"},
    {"id": 5,  "billNumber": "HB1814", "title": "Missing Middle Housing Act", "description": "Amends zoning division of IL Municipal Code. Requires large cities to allow middle housing development on large lots zoned residential. Requires smaller cities to allow development of at least duplexes on lots allowing detached single family dwellings. Prohibits applicable municipalities from discouraging development or regulating development in an inconsistent manner.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1814&DocTypeID=HB&LegId=159270&SessionID=114"},
    {"id": 6,  "billNumber": "HB1813", "title": "ADU Authorization Act", "description": "Amends the Control Over Building and Construction Article of the IL Municipal Code. Defines accessory dwelling unit and efficiency unit. Prohibits municipalities from prohibiting the building or use of ADUs and prohibits home rule units from acting inconsistently with the Act.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1813&DocTypeID=HB&LegId=159269&SessionID=114"},
    {"id": 7,  "billNumber": "HB3552", "title": "Local Accessory Dwelling Unit Act", "description": "Creates Local Accessory Dwelling Unit Act. Defines accessory dwelling unit, types of units, and discretionary review. Prohibits local governments from prohibiting the building or use of ADUs and sets requirements for ADU application review, timelines, delays, and processing. Prohibits home rule units from acting inconsistently with the Act.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3552&DocTypeID=HB&LegId=162242&SessionID=114"},
    {"id": 8,  "billNumber": "HB1843", "title": "Family Status Housing Protection Act", "description": "Amends the Zoning Division of the IL Municipal Code. Disallows classification, regulation, and restriction on use of property based on family relationship. Prohibits municipalities from adopting zoning regulations that prohibit 2 or more unrelated people from living together, and regulations that prohibit community-integrated living arrangements.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=1843&DocTypeID=HB&LegId=159333&SessionID=114"},
    {"id": 9,  "billNumber": "HB3288", "title": "Affordable Communities Act", "description": "Creates the Affordable Communities Act. Clarifies and defines middle housing types. Applies to zoning units with populations over 100,000 and prohibits regulations from preventing middle housing development. Requires these zoning units to adopt land use ordinances and amend zoning maps/ordinances to implement middle housing requirements. Allows IHDA to adopt emergency rules for implementing the Act's requirements.", "year": [2025, 2026], "status": "Not passed into law", "type": "Endorsed", "category": "Zoning", "url": "https://www.ilga.gov/Legislation/BillStatus?GAID=18&DocNum=3288&DocTypeID=HB&LegId=161778&SessionID=114"},
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
    {"id": 26, "billNumber": "HB4290", "title": "Prop Tx - Bill of Rights", "description": "Amends prop. tax code. Requires each property tax bill to contain certain information. Creates property taxpayer's bill of rights. Amends truth in taxation law.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4290&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 27, "billNumber": "HB4316", "title": "Prop Tx - Cert of Error - Veterans", "description": "Amends prop. tax code. Certificate of error may be issued any time if it relates to the homestead exemption for veterans with disabilities and veterans of WWII.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4316&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 28, "billNumber": "HB4317", "title": "Prop Tx - Assessment Limit", "description": "Amends prop. tax code. Equalized assessed value, other than long-term ownership, shall not exceed the value of the immediately preceding general assessment year, increased by the lesser of 3% or the percentage increase in the CPI.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4317&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 29, "billNumber": "HB4320", "title": "Prop Tx - Extensions", "description": "Amends prop. tax code. No taxing district can levy a tax that is more than 103% of the base amount unless certain requirements are met. The taxing authority can be exempt from the provisions if approved by referendum.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4320&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 30, "billNumber": "HB4356", "title": "Prop Tx - Refunds", "description": "Amends prop. tax code. Refund resulting from certain orders of the circuit court or from certificate of error will not be allowed unless filed within certain timeframe.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4356&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 31, "billNumber": "HB4357", "title": "Prop Tx - Decisions", "description": "Amends prop. tax code. BOR limited to evidence presented by complainant or agent, assessor, and taxing district. Oral hearing granted on request. BOR decisions require computer printout of results or brief written statement.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4357&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 32, "billNumber": "HB4358", "title": "Prop Tx - Revisions", "description": "Amends prop. tax code. Appraisals submitted by owner occupant must be prepared for ad valorem purposes, estimate value of property as of year at issue, and comply with rules of chief county assessment offficer or BOR.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4358&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 33, "billNumber": "HB4405", "title": "Prop Tx - Revisions", "description": "Amends prop. tax code. \"Veteran\" also includes those who were killed in the line of duty but were not IL residents at time of death.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4405&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 34, "billNumber": "SB2745", "title": "Prop Tx - Disabled Persons", "description": "Amends prop. tax code. Applicant who receives homestead exemption for persons with disabilities and submits documentation that they are totally and permanently disabled need not be reexamined to receive the exemption if they meet certain requirements.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2745&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 35, "billNumber": "SB2746", "title": "Prop Tx - Senior Freeze", "description": "Amends prop. tax code. For taxable years 2026 and after, max income limitation for low-income senior citizens assessment freeze homestead exemption is $75,000 for all qualified property.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2746&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 36, "billNumber": "SB2750", "title": "Prop Tx - Police Spouse", "description": "Amends prop. tax code. Property used as qualified residence by surviving spouse of a law enforcement officer killed in the line of duty prior to the expiration of the application period for the exemption is exempt.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2750&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 37, "billNumber": "SB3042", "title": "Prop Tx - Police and Fire", "description": "Amends prop. tax code. Creates homestead exemption of reduction of $5,000 from equalized assessed value of property of the surviving spouse of a police officer or firefighter who is killed in the line of duty.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3042&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 38, "billNumber": "SB2751", "title": "Prop Tx - Senior Freeze", "description": "If SB0642 becomes law in the form it passed both houses on October 31, 2025, a provision the prop. tax code concerning the low-income senior freeze exemption is amended.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2751&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 39, "billNumber": "SB3217", "title": "Prop Tx - Senior Freeze", "description": "Amends prop. tax code. Beginning in taxable year 2026, the maximum income limitation for low-income senior citizens assessment freeze homestead exemption shall be increased each year by the percentage increase in the Consumer Price Index.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3217&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 40, "billNumber": "SB2779", "title": "Revenue - Prop Tx Replace", "description": "Amends Dep. of Revenue Law of Civil Admin. Code. Provides DoR, with the Governor's OMB, shall conduct a study to determine feasibility of phasing out use of property taxes to fund school districts and replacing it with other state and local revenue streams.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2779&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 41, "billNumber": "HB5570", "title": "Revenue - Prop Tx Replace", "description": "Same as above^", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5570&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 42, "billNumber": "SB2798", "title": "Prop Tx - General Homestead", "description": "Amends prop. tax code. Provides maximum reductions for the general homestead exemption in each taxable year and limits on assessment increases. Requires surplus funds in special tax allocation fund be distributed as soon as possible.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2798&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 43, "billNumber": "SB2828", "title": "Cty/Muni CD - Building Inspector", "description": "Amends Counties Code and IL Muni. Code. Requires bulding inspectors to hold specified credentials or be licensed. Provides a grace period to acquire the certification or credentials. Requires those performing plumbing inspections to be licensed and exempt from the other provisions.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2828&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 44, "billNumber": "SB2830", "title": "Property Justice Act", "description": "Creates the Property Justice Act. Bans interest on sale-in-error refunds from error or omission. Limits interest rate if interest is permitted. Limits amount a tax purchaser may receive in sale-in-error refunds each year. Requires officials execute presale certifications. Creates Community Revitalization Property Trust. The Trust shall acquire parcels from scavenger sales in distressed munis, clear title, extinguish liens, package parcels for redevelopment, convey them for $1 to qualified local purchasers, and prioritize community-driven redevelopment.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2830&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 45, "billNumber": "SB2833", "title": "Prop Tx - Appeal", "description": "Amends prop. tax code. If bills for second installment of taxes are not mailed by deadlines set forth in the Code, deadlines set forth for application for judgment and order of sale must be extended by an additional 90 days.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2833&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 46, "billNumber": "SB2834", "title": "Prop Tx - Cert of Purchase", "description": "Amends prop. tax code. Provides limits on when a certificate of purchase may be issued following the conclusion of a tax sale.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2834&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 47, "billNumber": "SB2853", "title": "Prop Tx - Veterans Commissions", "description": "Amends prop. tax code. Requires amount of tax used to fund Veterans Assistance Commission to be printed on property tax bills.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2853&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 48, "billNumber": "SB2854", "title": "Prop Tx - Veterans - PTell", "description": "Amends prop. tax extension limitation law in prop. tax code. Special purpose levies to fund a veterans assistance commission are not included in a taxing district's aggregate extension.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2854&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 49, "billNumber": "SB2862", "title": "Prop Tx - Abatement", "description": "Amends prop. tax code. Municipalities may, by ordinance, designate an area as a retail improvement abatement area if it meets certain requirements. Owners of retail property in those areas may enter into agreements with taxing districts to abate all or a portion of taxes levied on the property. Agreement must require the property owner to make a special payment in lieu of the property taxes.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2862&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 50, "billNumber": "SB2871", "title": "Prop Tx - Disabilities - Renewal", "description": "Amends prop. tax code. Permanently applies provision allowing chief county assessment officer to renew the homestead exemption for persons with disabilities without an annual application.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2871&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 51, "billNumber": "SB2884", "title": "Landlord/Tenant - Various", "description": "Creates the Let the People Lift the Ban Act. Allows voters of a unit of local government to approve referendums allowing rent control, which stops other prohibitions on rent control from applying. Repeals the Retaliatory Eviction Act.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2884&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 52, "billNumber": "HB4555", "title": "Prop Tx - Board of Review", "description": "Amends prop. tax code. For boards of review in counties under township organization with less than 3 million residents, 3 citizens of the state will comprise the board of review, instead of 3 citizens of the county.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4555&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 53, "billNumber": "SB3471", "title": "Prop Tx - Board of Review", "description": "Same as above^", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3471&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 54, "billNumber": "HB4586", "title": "$DHS - Home Modifications", "description": "Appropriates $7,500,000 from the General Revenue Fund to DHS to make a grant to the Ilinois Network of Centers for Independent Living to administer and implement the Home Modification Program.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4586&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 55, "billNumber": "SB3260", "title": "$ISBE - Homeless Students", "description": "Appropriates $5,000,000 from the State Board of Education to award funding under the Education of Homeless Children and Youth State Grant Program to support programming for students at risk for or experiencing homelessness.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3260&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 56, "billNumber": "HB4589", "title": "Cty CD/Muni CD - Building Permit", "description": "Amends the Counties Code and IL Municipal Code. County boards and municipalities may not issue a building permit on a residential unit if the owner is in default on any mortgage.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4589&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 57, "billNumber": "HB4387", "title": "Corp Ownership Property", "description": "Creates the Corporate Ownership of Residential Property Act. Applicable companies are prohibited from owning more than 500 residential properties in IL, including residential property held by affiliated entities or persons. Each company owning more than 500 must register annually with the Dept. of Financial and Professional Regulation. Each company owning 200-500 residential properties must provide the Dept a list of all residential properties owned, disclosure of affiliated entities and beneficial owners, and an affirmation of compliance with the Act.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4387&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 58, "billNumber": "SB3501", "title": "Corp Ownership Real Estate", "description": "Creates Restock the Block Act. Imposes on a covered entity an annual fee of 10% of property value of each residential property owend by the entity in excess of 10 single family or 8 multifamily homes. The fee must be deposited into the Illinois Affordable Housing Trust Fund for public housing projects and developments and provide rental and mortgage assistance. Defines covered entity and makes exceptions, and institutional real estate investor. Makes it unlawful for covered entity to purchase, acquire, or offer to purchase or acquire any interest in residential property unless it has been listed for sale to the general public for at least 90 days. Covered entities that violate provisions may be subject to civil damages and penalties up to $250,000. The covered entity is required to submit to seller or agent for the seller a form stating they are a covered entity and file it within 3 days with the Department of Human Services. Makes conforming changes to the Illinois Affordable Housing Act.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3501&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 59, "billNumber": "HB4389", "title": "Starter Home Incentive Act", "description": "Creates the Starter Home Incentive Zone Act. Municipalities may establish a starter home incentive zone if they adopt any three of the five provided reform options. These municipalities will receive benefits from the Department of commerce and Economic Opportunity and may receive benefits from the Department of Transportation. They must submit a report each year about the zones for annual compliance.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Rental Registry; registration of corporate landlords / owners", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4389&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 60, "billNumber": "SB2912", "title": "Landlord-Tenant Fees", "description": "Amends Landlord and Tenant Act. Prohibits broker or agent who rents/leases residential property as agent from demanding or receiving payments or fees from a tenant/prospective tenant for any services as agent arising out of leasing. Prohibits landlowner, landlord, lessor, or sublessor from demanding or requiring a tenant/prospective tenant retain, hire, or engage a broker or agent and pay them a fee or commission as condition to applying for or leasing a rental unit. Persons alleging violation may bring a civil action against the person or entity alleged to have violated the Act, may be awarded injunctive relief, monetary relief, attorney's fees, and costs.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2912&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 61, "billNumber": "SB3363", "title": "Rental Fee Transparency", "description": "Amends Landlord and Tenant Act. Each recurring nonoptional fee must be on listing or accompanying link to a website for the property and on the first page of the lease in clear and conspicuous manner as part of the total cost of rent. If not explicitly included in cost of rent, landlord may not charge the fee on a recurring basis, and tenant is not liable on a recurring basis. All one-time nonoptional fees must be detailed on the first page of a lease in clear and conspicuous manner, and landlord may not charge the fee, and tenant is not liable for it, if not explicitly contained. Prohibits landlord from requiring tenant to acquire or maintain insurance policy covering damage or injury occurring in common areas. Any person alleging violation may bring civil action seeking actual damages, injunctive relief, and attorney's fees/costs.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3363&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 62, "billNumber": "SB2920", "title": "Prop Tx - Police and Fire", "description": "Amends prop. tax code. Provides that property used as a qualified residence by a police officer or firefighter with a duty-related disability is exempt from property taxation.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2920&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 63, "billNumber": "SB2929", "title": "Prop Tx - Omitted Property", "description": "Amends prop. tax code. Notice of omitted assessment must be delivered by certified mail, return receipt requested, to both the property address and property owner at their current address based on a search of ownership-related documents and the IL Secretary of State Department of Business Services database.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2929&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 64, "billNumber": "SB2964", "title": "Prop Tx - Appeals", "description": "Amends prop. tax code. Complainants before the Board of Review or Property Tax Appeal Board may represent themselves or designate a representative to appear before the board on their behalf. The description of rules and procedures provided by the Board of Review to the public must include an explanation that the taxpayer may appear pro se or be represented by any other person. The assessor or board of review has the burden of proving any contested matter of fact by a preponderance of the evidence (rather than clear and convincing evidence).", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=2964&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 65, "billNumber": "HB4931", "title": "Prop Tx - Appeals", "description": "Amends prop. tax code. Provides that a corporation, LLC, or partnership may be represented by an attorney or a non-attorney, including, but not limited to, an accountant or other tax representative.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4931&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 66, "billNumber": "SB3003", "title": "Prop Tx - Income Property", "description": "Amends prop. tax code. In counties where county board so provides, by ordinance or resolution, owners of income-producing properties in the county must file physical descriptions of their properties with the chief county assessment officer upon request. Request for information must include individualized statement specifying all physical description information the assessor's office has on record and that the owner may confirm the information if no changes are required. Imposes penalties if property owner fails to respond to a request. Amends the Freedom of Information Act to provide financial records and data related to real estate income, expenses, and occupancy submitted to a chief assessment officer, except if submitted as part of an assessment appeal, are exempt from disclosure.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3003&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 67, "billNumber": "HB5464", "title": "Prop Tx - Income Property", "description": "Same as above^", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5464&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 68, "billNumber": "SB3065", "title": "Prop Tx - Notice", "description": "Amends prop. tax code. Concerning notices of increased assessments, the chief county assessment officer must continue to accept appeals from the taxpayer for a period of not less than 30 business days from the later of the date the assessment notice is mailed or is published on the assessor's website.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3065&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 69, "billNumber": "SB3108", "title": "Prop Tx - Statement of Exemption", "description": "Amends prop. tax code. Each property tax bill must contain a statement of any exemption that was granted to the property in the immediately preceding tax year but was not granted in the current tax year.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3108&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 70, "billNumber": "SB3174", "title": "Prop Tx - 30-Year Homestead", "description": "Amends prop. tax code. Establishes homestead exemption for qualified property continuously owned, used, and occupied as primary residence by qualified taxpayer for at least 30 years prior to Jan. 1 of taxable year for which exemption would apply. Requires taxpayers granted exemption to reapply annually. Assessor or chief county assessment officer may determine eligibility by application, visual inspection, questionnaire, or other reasonable methods. Sets forth provisions concerning review of exemptions granted and defines \"qualified homestead property\" and \"qualified taxpayer\". Amends State Mandates Act to require implementation without reimbursement.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3174&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 71, "billNumber": "SB3189", "title": "Prop Tx - 30-Year Homestead", "description": "Same as above^", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3189&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 72, "billNumber": "HB4603", "title": "$IHDA - 1st Gen Homebuyer Assist", "description": "Appropriates $50,000,000 from the General Revenue Fund to IHDA for depositing into the First-Generation Homebuyer Down Payment Assistance Fund to provide down payments and closing costs assistance to eligible first-generation homebuyers, and other administrative expenses under that program.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4603&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 73, "billNumber": "HB4626", "title": "Prop Tx - Homestead Exemption", "description": "Amends prop. tax code. For taxable years 2026 and after, the amount of general homestead exemption is the sum of (1) $10,000 in counties with 3 million or more inhabitants, $8,000 in counties contiguous to those, and $6,000 in all other counties; plus (2) the difference between equalized assessed value for the property in the current taxable year and equalized assessed value for the property in the base year.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4626&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 74, "billNumber": "HB4637", "title": "Prop Tx - Omitted Property", "description": "Amends prop. tax code. In counties with less than 3 million inhabitants, a property that receives an erroneous hoemstead exemption for the current or prior 3 assessments years may be considered omitted property. Provides for penalties and interest to be imposed on that property and arrearage of taxes or interest that might have been assessed against the property shall not be chargeable to certain bona fide purchasers of the property.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4637&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 75, "billNumber": "HB4800", "title": "Loc Gov Buliding Permit Act", "description": "Creates Local Government Building Permit Act. Applies to units of local gov. that require a person to obtain a permit from the local gov. before constructing a building. Requires local gov. to comply with timelines for issuing building permits. If local gov. fails to comply with timelines, the permit is automatically approved unless proposed project violates published building or zoning codes. Local gov. must publish specific information concerning permits on its website. Fees imposed to approve permit application may not exceed actual cost incurred from reviewing it. Persons denied a building permit may appeal to Building Permit Ombudsman. Creates Building Permit Ombudsman position within Dept of Commerce and Economic Opportunity, who shall receive, review, and resolve appeals brought under the Act.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4800&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 76, "billNumber": "HB4841", "title": "Inc Tx - Affordable Housing", "description": "Amends Illinois Income Tax Act. The tax credit for affordable housing donations applies permanently.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4841&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 77, "billNumber": "HB4946", "title": "Prop Tx - Taxing District Prop", "description": "Amends prop. tax code. Property leased, subleased, or rented, in whole or in part, to a taxing district and used exclusively for a bona fide taxing district purpose is exempt. Exemption applies only to the portion of property used for bona fide taxing district purposes.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4946&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 78, "billNumber": "HB4952", "title": "Prop Tx - Veterans Disability", "description": "Amends prop. tax code. In granting homestead exemption for veterans with disabilities, for taxable year 2025 and after, if the veteran has a service connected disability of 60% or more, property is exempt from taxation (currently at 70% or more, then first $250,000 in equalized assessed value is exempt.)", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=4952&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 79, "billNumber": "HB5378", "title": "Prop Tx - Veterans w/Disability", "description": "Amends prop. tax code. In granting homestead exemptions for veterans with disabilities and veterans of World War II, if the veteran has a service-connected disability of 50% or more, the first $250,000 in equalized assessed value of the property is exempt from taxation.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5378&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 80, "billNumber": "HB5009", "title": "Prop Tx - Assessment Limit", "description": "Amends prop. tax code. Any change in assessment resulting from reassessment in the general assessment year shall not exceed the lesser of (1) 3% of assessed value for prior year; or (2) percentage change in the Consumer Price Index during the 12-month calendar year preceding the assessment year. Limitation does not apply if the increase is attributable to an addition, improvement, or modification to the property.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5009&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 81, "billNumber": "SB3540", "title": "Prop Tx - Assessment Limit", "description": "Amends prop. tax code. Any change in assessment resulting from reassessment in the general assessment year shall not exceed assessed value of the property in the last general assessment year multiplied by one plus the percentage change in the Consumer Price Index during the 12-month calendar year preceding the general assessment year for which reassessment is conducted. Limitation does not apply if the increase is attributable to an addition, improvement, or modification to the property.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3540&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 82, "billNumber": "HB5075", "title": "Prop Tx - Surplus", "description": "Amends prop. tax code. Within 30 days of recording a tax deed for residential property, the tax deed grantee must pay the surplus to the previous owner of the property described in the deed. Sets forth the procedures to calculate the surplus.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Property Taxes", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5075&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 83, "billNumber": "HB5123", "title": "Inc Tx - Prop Tx Credit", "description": "Amends Illinois Income Tax Act. If the amount of the credit for residential real estate property taxes excees the taxpayer's liability, that amount shall be refunded if the taxpayer is 65 or older and has a federal adjusted gross income of no more than $50,000. The credit is exempt from the Act's automatic sunset provision.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5123&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 84, "billNumber": "HB5200", "title": "Prop Tx - Municipal Workers", "description": "Amends prop. tax code. Grants a homestead exemption for property that is located in a county with 1 million or more inhabitants and is owned and occupied as a principal residence during the taxable year by a qualified municipal worker. The amount of the exemption shall be a reduction from the equalized assessed value of the property in an amount equal to 5% of the equalized assessed value of the property.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5200&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 85, "billNumber": "HB5234", "title": "Landlord-Tenant Fees", "description": "Amends Landlord and Tenant Act. Requires landlords disclose all non-optional fees in clear and conspicuous manner in listing and on first page of lease. If landlord fails to comply, they may not collect the fee. Prohibits landlords from charging a bundled services fee that combines optional and non-optional fees. Prohibits landlords from charging tenant with a fee/fine that includes an application fee including a background check of more than $50, an after-hours request for maintenance service, or pest abatement or removal in which tenant has not contributed to infestation. Prohibits landlords from charging tenant more than one of security deposit, move-in fee, or move-out fee. Exempts leases in owner-occupied buildings with 6 or fewer units and to nonresidential tenancies. Creates civil cause of action for violation of the Act by landlord.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5234&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 86, "billNumber": "SB3763", "title": "Landlord-Tenant Fees", "description": "Same as above^", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3763&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 87, "billNumber": "HB5245", "title": "Prop Tx - Seniors Level Billing", "description": "Amends prop. tax code. For all applicants who meet the household income and other qualifications for the Low-Income Senior Citizens Assessment Freeze Homestead Exemption, for property bills prepared for 2026 and after, the county collector shall bill the household an amount not to exceed their bill for the prior year. Provides an exception to level tax billing when an assessed improvement is made by owner or occupant. Eligibility is contingent upon continuing eligibility for the homestead exemption.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5245&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 88, "billNumber": "HB5257", "title": "Home Illinois Program", "description": "Amends Department of Human Services Act. If a municipality with a population of 500,000 or more that receives grant funding from DHS for emergency and transitional housing fails to achieve compliance with federal and state discrimination laws by July 1, 2027, DHS shall require 30% of funds allocated to go toward improving accessibility and achieving compliance with discrimination laws.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5257&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 89, "billNumber": "HB5267", "title": "Short-Term Rental Assessment", "description": "Amends prop. tax code. In counties with a population of 200,000 or more that classify property, any residential property used as a short-term rental for 30 or more days in any year shall be assessed on the same basis as commercial property.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5267&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 90, "billNumber": "HB5325", "title": "Prop Tx - CILA Exempt", "description": "Amends prop. tax code. Certain property on which a community-integrated living arrangement is located is entitled to a reduction in its equalized assessed value in an amount equal to the product that results when the number of occupants who use it as a primary residence is multiplied by $2,000. Property qualifies for the homestead exemption for persons with disabilities even if the person is not an owner of record or liable for paying property taxes if a family member of the person meets those criteria.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5325&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 91, "billNumber": "HB5371", "title": "Prop Tx - PTell Chicago", "description": "Amends Property Tax Extension Limitation Law in the Property Tax Code. The City of Chicago is considered a taxing district for purposes of the Law. Preempts home rule powers.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5371&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 92, "billNumber": "HB5372", "title": "Prop Tx - Cert of Purchase", "description": "Amends prop. tax code. For tax sales occurring on or after Jan. 1, 2027, a certificate of purchase shall not be issued sooner than 90 days after the conclusion of the tax sale.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5372&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 93, "billNumber": "HB5394", "title": "Hum Rts - Credit Scores", "description": "Amends Illinois Human Rights Act. It is a civil rights violation to refuse to lease/rent property or otherwise discriminate in terms, conditions, or privileges of a real estate transaction by using credit score or history as a disqualifying factor if the applicant's source of income includes a subsidy. Use of scores or history to deny a rental application to a person with a housing subsidy is a violation as a practice that subjects individuals to discrimination based on source of income without a legitimate, nondiscriminatory necessity.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5394&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 94, "billNumber": "SB3475", "title": "Human Rights - Landlord - Tenant", "description": "Amends Illinois Human Rights Act. It is a violation of the Real Estate Transactions Article to unlawfully discriminate using credit score and history, including insufficient credit history. Limited only to landlord and tenant agreements in which a tenant or prospective tenant is seeking to use a rental subsidy.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3475&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 95, "billNumber": "HB5424", "title": "IHDA - Housing Planning", "description": "Amends the Comprehensive Housing Planning Act. Requires the state to prepare and be guided by 3-year comprehensive housing plan, consistent with affirmative fair housing provisions of the IL Human Rights Act and specifically addresses specified underserved populations. Requires the plan to reflect the state's commitment to an affordable housing approach for priority populations that promotes access to opportunity and resources. Expands membership of the State Housing Task Force to include Directors or Secretaries of several state departments and agencies. Requires the task force to, in addition to other activities, adopt a mission statement, oversee implementation of the plan, vote on research questions and affordable housing topics. Prohibits IHDA from directly or indirectly having a financial interest in an Authority contract.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5424&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 96, "billNumber": "HB5433", "title": "Prop Tx - Circuit Breaker", "description": "Creates the Circuit Breaker Property Tax Relief Act. Individuals domiciled in the state, eligible for and receiving a homestead exemption, who have experienced property tax bill spikes, and who have an income within a specified limitation are eligible for a grant of a portion of their property tax bill spike. The maximum grant amount is 50% of the individual's tax bill spike. Creates the Circuit Breaker Property Tax Relief Fund to make grants.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5433&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 97, "billNumber": "HB5484", "title": "Fair Access to Housing", "description": "Amends the Fair Access to Housing Act. On and after Jan. 1, 2027, it will be unlawful for a covered entity to purchase, acquire, or offer to purchase or acquire any interest in a single-family residence unless it has been listed for sale to the general public for at least 75 days. Defines \"covered entity\".", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5484&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 98, "billNumber": "HB5543", "title": "Prop Tx - Interest Penalty", "description": "Amends prop. tax code. If interest penalty for delinquent taxes is imposed, and if collections are enjoyed by a county,  collector must place all proceeds into separate and distinct fund for distribution. All moneys in the fund created by each county must, within 30 days of receipt, be divided and distributed to the county and all other proper authorities or persons on the basis of proportionate share of  overall tax extension within which delinquency and payment of penalties took place. When making the distribution, the collector may include a notification that the money is a result of interest penalties charged by the county.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5543&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 99, "billNumber": "HB5547", "title": "Prop Tx - Sex Offender Prohibit", "description": "Amends prop. tax code. Beginning in 2027, no property used as the primary residence of a child sex offender during the year may receive a homestead exemption.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5547&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 100, "billNumber": "HB5549", "title": "Prop Tx Extension Cap", "description": "Amends prop. tax code. Whether or not a county is subject to property tax extension limitation law, if it has enjoyed and continues to enjoy aggregate extension increase of at least 4.5% per year, cumulatively and in compound fashion for at least 3 years, in the fourth and all succeeding years the county will be subject to an aggregate extension limitation increase not to exceed 3% per year. An exception will be enjoyed by a county that successfully seeks approval by referendum from release from cap on countywide aggregate extensions.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5549&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 101, "billNumber": "HB5612", "title": "Revenue - Prop Tx Relief", "description": "Amends the School Code. State Board of Education will establish and administer a program to award property tax relief grants to school districts in the State. In exchange for receiving a grant, a school district's maximum aggregate property tax extension for the taxable year may not exceed its adjusted maximum aggregate property tax extension for that year.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5612&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 102, "billNumber": "HB5615", "title": "Property Records - Housing", "description": "Amends Financial Institutions Act. Dept. of Financial and Professional Regulation must establish, maintain, publish on website registry of nominees of mortgages. Amends Counties Code. Each county board must adopt revisions to its fee schedule to include additional $150 fee for nominee of a mortgage to record a mortgage, including assignment, extension, amendment, or subordination. Exception for recording of release of mortgage by nominee. Additional fee is collected as Rental Housing Support Program State surcharge and deposited into the Fund, and $30 is collected as county fee with $25 used for development and maintenance of affordable housing capacity and $5 to defray cost of electronic or automated access to county's property records. Amends Code of Civil Procedure. Lien is not created if nominee of mortgage fails to provide recorder with cover sheet. Amends Conveyances Act. Mortgages or assignments recorded by or for a nominee must be recorded with cover sheet explaining fees charged, identity of nominee, and process to be used by mortgagor to track the mortgage.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=5615&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 103, "billNumber": "SB3703", "title": "Property Records - Housing", "description": "Same as above^", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3703&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 104, "billNumber": "SB3671", "title": "Rental Property Registry", "description": "", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3671&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 105, "billNumber": "SB3187", "title": "Development on Church Land Act", "description": "Creates Faith-Based Housing and Mixed-Use By-Right Act. Local government will permit multifamily and mixed-use developments as allowable by-right uses on faith-based land. A local government may not require proposed development on faith-based land to obtain discretionary approval to permit  use and development, or allow for the minimum development standards and limitations established by the Act. Provides by-right entitlement applies whether or not the faith-based organization continues to operate an existing religious, educational, or community facility on the same or adjacent parcel, and regardless of whether  housing is owned, leased, operated, or developed by the organization or a partner acting under agreement. A local govenrment will approve an application for multifamily or mixed-use development on faith-based land if it satisfies their generally applicable, objective land development and building regulations.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3187&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 106, "billNumber": "SB3212", "title": "Transit Opportunity Zone Act", "description": "Creates Transit-Oriented Overlay and Opportunity Retail Integration Zoning Act. Areas within a 1 mile radius of a transit-oriented development is an ORI zone - created automatically. Within ORI Zone, certain uses will be permitted by right: retail, restaurant, personal service establishments; office, professional, medical, administrative uses; residential uses of all types; light manufacturing, research, etc.; institutional, education, cultural, government uses; lodging, hospitality uses; structured, accessory parking facilities; and other substantially similar use. A local government may enforce objective development standards applicable within the ORI zone. If it does not approve a proposal for a development in an ORI zone for use permitted within it within 90 days after receiving application, the development proposal is deemed approved.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3212&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 107, "billNumber": "SB3457", "title": "Prop Tx - Notice to Tennant", "description": "Amends prop. tax code. If residential property is subject to an application for judgment and sale for delinquent taxes, the county collector must notify all known occupants of those dwelling units that an application for judgment and sale has been filed.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3457&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 108, "billNumber": "HB0598", "title": "Government - Tech", "description": "House Amendment 001 delays the 2023 annual sale that would normally have been held in 2025 to December 2026.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=598&GAID=18&DocTypeID=HB&SessionID=114"},
    {"id": 109, "billNumber": "SB3476", "title": "Landlord - Tenant - Rent", "description": "Amends the Landlord and Tenant Act. \"Rent\" means any money or other consideration given for the right to use, possess, or occupy property.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3476&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 110, "billNumber": "SB3477", "title": "Eviction Moratorium", "description": "Amends Code of Civil Procedure. Creates an eviction moratorium for residential real estate for 12-month period against tenant or member of their household who (1) has been unable to work because of detention by immigration authorities; or (2) has experienced termination of federal benefits; and (3) detention or benefit termination has materially affected their ability to pay rent. Prohibits landlord from commencing or continuing a residential eviction action of a tenant covered under the Act, and from charging fees or penalties related to nonpayment. IHDA may adopt rules to create the required form for a declaration.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3477&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 111, "billNumber": "SB3490", "title": "Prohibited Prop Ownership", "description": "Amends Property Owned by Noncitizens Act. Prohibited foreign-party-controlled businesses may not acquire interest in land in the state. A prohibited business in violation has 2 years to divest, and if they do not, the Attorney General will commence action in circuit court. A prohibited party may not acquire interest in agricultural land regardless of whether they intend to use it for nonfarming purposes. Prohibited parties who are resident alients have the right to acquire and hold agricultural land upon same terms as a citizen during residence, but if no longer a resident alien, they have 2 years to divest or Attorney General will commence an action. If a prohibited party that owns agricultural land or a prohibited business violates any Act provisions, the violation may be a class 4 felony punishable by up to 2 years' imprisonment or a $15,000 fine, or both. Creates Office of Agricultural Intelligence within the Department of Agriculture.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3490&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 112, "billNumber": "SB3494", "title": "Prop Tx - Forced Sale", "description": "Amends prop. tax code. For tax sales that occur on or after the effective date of the Act, the redemption period will be 5 years instead of 2.5. A tax deed grantee may file a petition in circuit court forcing a judicial sale of the property. Provides for distribution of surplus funds.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Property Taxes", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3494&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 113, "billNumber": "SB3504", "title": "Rental Payment Info - Reporting", "description": "Amends Landlord and Tenant Act. Any landlord of a unit of residential property must offer tenants the option of having rental payment information reported to at least one nationwide consumer reporting agency as long as it resells or furnishes the information to a nationwide consumer reporting agency. Defines \"rental payment information\". Requires before reporting tenant's rental history information, landlord must provide written notice of offer and obtain written authorization from tenant. If a tenant elects to have their information reported, landlord may require tenant to pay a fee not to exceed actual cost to the landlord to provide the service plus $5 per month. Payment or nonpayment of the fee may not be reported. Exempts landlords of residential rental buildings with 15 or fewer units unless they own more than one rental building, and are a corporation, LLC in which a member is a corporation, or a real estate investment trust.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3504&GAID=18&DocTypeID=SB&SessionID=114"},
    {"id": 114, "billNumber": "SB3530", "title": "Rent - Security Deposits", "description": "Amends Landlord and Tenant Act. Prohibits total security deposit from exceeding first full month's rent for dwelling that is primary residence of the tenant. Landlord may only charge tenant a security deposit upon signing of an intial lease agreement. Prohibits landlord from charging tenant additional security deposit or increase total amount of a deposit upon renewal of lease or increase in rent. Prohibits landlord from increasing rent by more than 3.5% in 12-month period for dwelling that is tenant's primary residence. Requires landlord provide tenant with a minimum of 30 days' written notice before increasing rent. If written notice is not provided, tenant is not liable for difference between initial rent and the increased rent. Any person alleging violation of the provisions may bring a civil action and the court may order injunctive relief, monetary relief, attorney's fees, and costs.", "year": [2026], "status": "Not passed into law", "type": "Watching", "category": "Other", "url": "https://www.ilga.gov/Legislation/BillStatus?DocNum=3530&GAID=18&DocTypeID=SB&SessionID=114"},
]


def parse_bill_number(bill_number):
    """Parse 'HB3466' → ('HB', '3466')."""
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
    """Extract lastAction text and date from <lastaction> element."""
    la_el = root.find("lastaction")
    if la_el is None:
        return "", ""
    action_el = la_el.find("action")
    date_el   = la_el.find("statusdate")
    last_action      = (action_el.text or "").strip() if action_el is not None else ""
    last_action_date = (date_el.text   or "").strip() if date_el   is not None else ""
    return last_action, last_action_date


def get_primary_sponsor(root):
    """Extract the chief sponsor name from <sponsor><sponsors> text."""
    sponsor_el = root.find("sponsor")
    if sponsor_el is None:
        return ""
    sponsors_el = sponsor_el.find("sponsors")
    if sponsors_el is None or not sponsors_el.text:
        return ""
    first = re.split(r'-|,|\s+and\s+', sponsors_el.text.strip())[0].strip()
    return first


def get_action_texts(root):
    """Collect all <action> texts from the flat children of <actions>."""
    texts = []
    actions_el = root.find("actions")
    if actions_el is not None:
        for child in actions_el:
            if child.tag.lower() == "action" and child.text:
                texts.append(child.text.strip().lower())
    return texts


MONTH_MAP = {'Jan':'1','Feb':'2','Mar':'3','Apr':'4','May':'5','Jun':'6',
             'Jul':'7','Aug':'8','Sep':'9','Oct':'10','Nov':'11','Dec':'12'}

def get_next_action(root):
    """Parse next scheduled action from <nextaction> or <committeehearing>.

    Returns (date_str, action_type_str) — both empty strings if not found.
    """
    na = root.find("nextaction")
    if na is not None:
        date_el   = na.find("statusdate")
        action_el = na.find("action")
        if date_el is not None and date_el.text:
            date_str   = date_el.text.strip()
            action_str = (action_el.text or "").strip() if action_el is not None else ""
            return date_str, action_str
    # Fallback: <committeehearing> plaintext
    ch = root.find("committeehearing")
    if ch is not None and ch.text:
        raw = ch.text.strip()
        m = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(\d{4})\b', raw)
        if m:
            date_str   = f"{MONTH_MAP[m.group(1)]}/{m.group(2)}/{m.group(3)}"
            action_str = raw[:m.start()].strip() or ""
            return date_str, action_str
    return "", ""


def get_amendments(root):
    """Return (last_amendment_name, last_amendment_date, is_shell_bill).

    Parses <synopsis> for the last non-empty <synopsistitle> and its <SynopsisText>.
    Shell bill = any amendment SynopsisText starts with 'Replaces everything after the enacting clause'.
    Date = first action in <actions> that mentions the last amendment name.
    """
    synopsis_el = root.find("synopsis")
    last_name = None
    is_shell  = False

    if synopsis_el is not None:
        current_title = None
        for child in synopsis_el:
            if child.tag == "synopsistitle":
                t = (child.text or "").strip()
                if t:
                    current_title = t
            elif child.tag == "SynopsisText" and current_title:
                text = (child.text or "").strip()
                last_name = current_title
                if text.startswith("Replaces everything after the enacting clause"):
                    is_shell = True
                current_title = None

    last_date = _find_amendment_date(root, last_name) if last_name else None
    return last_name or None, last_date or None, is_shell


def _find_amendment_date(root, amendment_name):
    """Return date of the first action entry mentioning amendment_name."""
    actions_el = root.find("actions")
    if actions_el is None:
        return None
    current_date = None
    for child in actions_el:
        if child.tag == "statusdate":
            current_date = (child.text or "").strip()
        elif child.tag == "action" and amendment_name:
            if amendment_name.strip() in (child.text or ""):
                return current_date
    return None


def map_stage(last_action, action_history, doc_type):
    """Map last action + action history to a stage label."""
    la = last_action.lower()

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

    history = " ".join(action_history)
    if "passed house" in history or "arrive in senate" in history:
        return "In Senate Committee"
    elif "passed senate" in history or "arrive in house" in history:
        return "In House Committee"
    else:
        return "In House Committee" if doc_type == "HB" else "In Senate Committee"


def _ilga_fields_from_xml(xml_bytes, bill_number, prev_stage, prev_stage_changed_at, fetched_at):
    """Parse XML bytes and return the computed ILGA fields dict.

    Returns None if XML parsing fails, signalling the caller to use fallback values.
    """
    doc_type, _ = parse_bill_number(bill_number)
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"    WARNING: XML parse error for {bill_number}: {e}", file=sys.stderr)
        return None

    last_action, last_action_date = get_last_action_fields(root)
    action_history  = get_action_texts(root)
    primary_sponsor = get_primary_sponsor(root)
    new_stage       = map_stage(last_action, action_history, doc_type)
    next_action_date, next_action_type = get_next_action(root)
    last_amendment_name, last_amendment_date, is_shell_bill = get_amendments(root)

    # stageChangedAt: update only if stage has changed
    if new_stage != prev_stage:
        stage_changed_at = fetched_at
    else:
        stage_changed_at = prev_stage_changed_at or fetched_at

    print(f"    stage={new_stage}  sponsor={primary_sponsor}  lastAction={last_action[:60]}")

    return {
        "stage":             new_stage,
        "primarySponsor":    primary_sponsor,
        "lastAction":        last_action,
        "lastActionDate":    last_action_date,
        "ilgaFetchedAt":     fetched_at,
        "stageChangedAt":    stage_changed_at,
        "nextActionDate":    next_action_date or None,
        "nextActionType":    next_action_type or None,
        "lastAmendmentName": last_amendment_name,
        "lastAmendmentDate": last_amendment_date,
        "isShellBill":       is_shell_bill,
    }


def process_bill(bill, prev_data):
    """Fetch ILGA XML and return updated bill dict. Falls back to previous data on error."""
    bill_number = bill["billNumber"]
    url = get_xml_url(bill_number)
    print(f"  {bill_number} -> {url}")

    prev         = prev_data.get(bill_number, {})
    fetched_at   = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev_stage   = prev.get("stage")
    prev_sca     = prev.get("stageChangedAt")

    xml_bytes = fetch_xml(url)
    if xml_bytes is None:
        return {
            **bill,
            "stage":             prev.get("stage",             "Unknown"),
            "primarySponsor":    prev.get("primarySponsor",    ""),
            "lastAction":        prev.get("lastAction",        ""),
            "lastActionDate":    prev.get("lastActionDate",    ""),
            "ilgaFetchedAt":     prev.get("ilgaFetchedAt",     ""),
            "stageChangedAt":    prev.get("stageChangedAt",    ""),
            "nextActionDate":    prev.get("nextActionDate"),
            "nextActionType":    prev.get("nextActionType"),
            "lastAmendmentName": prev.get("lastAmendmentName"),
            "lastAmendmentDate": prev.get("lastAmendmentDate"),
            "isShellBill":       prev.get("isShellBill",       False),
        }

    fields = _ilga_fields_from_xml(xml_bytes, bill_number, prev_stage, prev_sca, fetched_at)
    if fields is None:
        return {
            **bill,
            "stage":             prev.get("stage",             "Unknown"),
            "primarySponsor":    prev.get("primarySponsor",    ""),
            "lastAction":        prev.get("lastAction",        ""),
            "lastActionDate":    prev.get("lastActionDate",    ""),
            "ilgaFetchedAt":     prev.get("ilgaFetchedAt",     ""),
            "stageChangedAt":    prev.get("stageChangedAt",    ""),
            "nextActionDate":    prev.get("nextActionDate"),
            "nextActionType":    prev.get("nextActionType"),
            "lastAmendmentName": prev.get("lastAmendmentName"),
            "lastAmendmentDate": prev.get("lastAmendmentDate"),
            "isShellBill":       prev.get("isShellBill",       False),
        }

    return {**bill, **fields}


def process_user_bill(bill, fetched_at):
    """Refresh ILGA fields for a user-added bill, preserving user-set fields.

    Preserves: title, description, category, type, userAdded, id, year, status, url.
    Updates: stage, primarySponsor, lastAction, lastActionDate, ilgaFetchedAt,
             stageChangedAt, nextActionDate, nextActionType.
    """
    bill_number = bill["billNumber"]
    url = get_xml_url(bill_number)
    print(f"  [user] {bill_number} -> {url}")

    prev_stage = bill.get("stage")
    prev_sca   = bill.get("stageChangedAt")

    xml_bytes = fetch_xml(url)
    if xml_bytes is None:
        return bill  # keep existing values

    fields = _ilga_fields_from_xml(xml_bytes, bill_number, prev_stage, prev_sca, fetched_at)
    if fields is None:
        return bill

    # Merge: start from bill (preserves user fields), overlay with ILGA fields
    return {**bill, **fields}


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


def load_user_bills(user_bills_path):
    """Load user-bills.json; returns empty list if missing or invalid."""
    if not user_bills_path.exists():
        return []
    try:
        with open(user_bills_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def main():
    repo_root       = Path(__file__).parent.parent
    output_path     = repo_root / "data" / "bills.json"
    user_bills_path = repo_root / "data" / "user-bills.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prev_data = load_previous_data(output_path)
    print(f"Updating {len(BILLS)} base bills -> {output_path}\n")

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

    # ── Refresh user-added bills ──────────────────────────────────────────────
    user_bills = load_user_bills(user_bills_path)
    if user_bills:
        print(f"\nRefreshing {len(user_bills)} user-added bill(s) -> {user_bills_path}")
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        updated = [process_user_bill(b, fetched_at) for b in user_bills]
        with open(user_bills_path, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2, ensure_ascii=False)
        print(f"Done. Refreshed {len(updated)} user-added bill(s).")
    else:
        print("\nNo user-added bills to refresh.")


if __name__ == "__main__":
    main()
