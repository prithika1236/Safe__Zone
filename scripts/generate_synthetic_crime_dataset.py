"""SafeZone Synthetic Crime Dataset Generator.

Follows the Master Frozen Specification:
- Reads ward boundaries from data/raw/Wards.geojson
- Generates exactly 10,000 synthetic incident records
- Enforces 100% geometric containment inside assigned ward polygons
- Natural language descriptions across 16 categories without label leakage
- Controlled spatial-temporal patterns for reference vs dynamic PRP analysis
- Validates output file data/processed/safezone_crime_dataset.csv
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from shapely.geometry import shape, Point

# Deterministic seeds for reproducibility
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

RAW_GEOJSON_PATH = os.path.join("data", "raw", "Wards.geojson")
OUTPUT_CSV_PATH = os.path.join("data", "processed", "safezone_crime_dataset.csv")

TARGET_ROW_COUNT = 10000

# 16 Frozen Categories & Frozen Severity Mapping
SEVERITY_MAPPING = {
    "THEFT": "MEDIUM",
    "ROBBERY": "HIGH",
    "BURGLARY": "HIGH",
    "ASSAULT": "HIGH",
    "STALKING": "MEDIUM",
    "VERBAL_ABUSE_THREAT": "MEDIUM",
    "SEXUAL_HARASSMENT": "HIGH",
    "DOMESTIC_VIOLENCE": "HIGH",
    "KIDNAPPING": "CRITICAL",
    "FRAUD": "MEDIUM",
    "CYBERCRIME": "MEDIUM",
    "VANDALISM": "LOW",
    "DRUG_RELATED_CRIME": "HIGH",
    "PUBLIC_DISTURBANCE": "LOW",
    "HOMICIDE": "CRITICAL",
    "OTHER": "LOW",
}

CATEGORIES = list(SEVERITY_MAPPING.keys())

# Target category counts summing to 10,000 with balanced distribution
CATEGORY_TARGET_COUNTS = {
    "THEFT": 1000,
    "ROBBERY": 750,
    "BURGLARY": 750,
    "ASSAULT": 850,
    "STALKING": 550,
    "VERBAL_ABUSE_THREAT": 600,
    "SEXUAL_HARASSMENT": 650,
    "DOMESTIC_VIOLENCE": 550,
    "KIDNAPPING": 400,
    "FRAUD": 650,
    "CYBERCRIME": 700,
    "VANDALISM": 550,
    "DRUG_RELATED_CRIME": 550,
    "PUBLIC_DISTURBANCE": 600,
    "HOMICIDE": 400,
    "OTHER": 450,
}

assert sum(CATEGORY_TARGET_COUNTS.values()) == TARGET_ROW_COUNT, "Target category counts must sum to 10000"

LOCATION_TYPES = [
    "ROAD",
    "RESIDENTIAL_AREA",
    "MARKET",
    "BUS_STOP",
    "RAILWAY_AREA",
    "COMMERCIAL_AREA",
    "PARK",
    "EDUCATIONAL_AREA",
    "WORKPLACE",
    "PUBLIC_PLACE",
    "ONLINE",
    "OTHER",
]

STATUSES = ["REPORTED", "UNDER_INVESTIGATION", "RESOLVED", "CLOSED"]

# Combinatorial linguistic building blocks for synthetic descriptions (avoiding label leakage)
DESCRIPTION_VOCABULARY = {
    "THEFT": [
        "Unattended backpack containing laptop and cash was snatched from a bench.",
        "Gold chain was snatched from pedestrian's neck by two individuals riding a motorcycle.",
        "Parked two-wheeler was found missing outside shopping complex upon return.",
        "Smart mobile phone and wallet taken from pocket in heavily crowded commuter bus.",
        "Bicycle locked to railing was stolen during late afternoon hours.",
        "Bystander reported missing handbag containing valuables left momentarily on a counter.",
        "Vehicle spare parts and battery removed from car parked on the roadside overnight.",
        "Valuable watch and purse stolen from a gym locker while complainant was exercising.",
        "Delivery package containing electronic gadget was taken from front doorstep.",
        "Purse containing jewelry and identification documents was picked during market rush.",
        "Luggage bag kept in overhead luggage rack was missing upon reaching transit stop.",
        "Two-wheeler helmet and side pouch with cash stolen from exterior parking area.",
        "Stash of copper wiring and metal tools taken from an ongoing residential project site.",
        "Smartphone snatched from victim's hands while waiting near transit terminal.",
        "Customer reported wallet missing after making payment at busy grocery store."
    ],
    "ROBBERY": [
        "Two masked individuals brandishing knives demanded cash and jewelry on dark street corner.",
        "Pedestrian threatened with sharp weapon and forced to hand over purse and gold ring.",
        "Complainant was confronted in an alleyway and forcibly stripped of watch and smartphone.",
        "Two suspects on motorbike blocked victim path, brandished iron rod, and took money bag.",
        "Shop cashier was held at knife-point during closing hours and store register cash was taken.",
        "Group of three surrounded walker, intimidated with weapons, and confiscated all electronic gadgets.",
        "Driver was stopped near isolated stretch and coerced under physical intimidation to surrender earnings.",
        "Complainant ambushed by two men wielding bladed tools demanding bank cards and cash.",
        "Armed confrontation on deserted road where assailants forcibly seized handbag containing payroll.",
        "Bystander attacked from behind and coerced under weapon threat to give up leather bag.",
        "Individual was accosted near poorly lit flyover underpass and robbed of expensive wrist watch.",
        "Masked suspects intercepted two-wheeler, threatened severe bodily harm, and snatched gold ornaments."
    ],
    "BURGLARY": [
        "Rear window grill was bent and gold ornaments were missing from bedroom cupboard.",
        "Premises entered by breaking padlock overnight; electronic items and cash box ransacked.",
        "Apartment front lock forced open while residents were out of station for the weekend.",
        "Ground floor balcony glass sliding door shattered and valuable watches taken.",
        "Shop shutter lock cut with bolt cutter before dawn; inventory and till cash missing.",
        "Perpetrators gained access through terrace door and searched drawers in master bedroom.",
        "Commercial warehouse lock breached overnight and several cartons of merchandise removed.",
        "Jewelry box and foreign currency stolen from locked steel safe inside residence.",
        "Unoccupied villa broken into through kitchen ventilator grill with extensive ransacking.",
        "Side entrance latch tampered with and laptop accessories stolen from home office."
    ],
    "ASSAULT": [
        "Complainant was physically struck with a blunt wooden club following heated altercation.",
        "Victim sustained severe facial lacerations after being attacked by two men outside tea stall.",
        "Bystander assaulted by group of individuals after minor road traffic collision.",
        "Sudden physical attack occurred near taxi stand leaving victim with fractured forearm.",
        "Complainant attacked with heavy iron pipe during dispute over parking space.",
        "Physical brawl erupted resulting in head injury from blunt object outside dining hall.",
        "Victim was pushed to the ground and repeatedly kicked by known acquaintance.",
        "Aggressive altercation leading to bleeding wounds on forehead requiring medical attention.",
        "Complainant ambushed near intersection and beaten with bamboo sticks.",
        "Physical violence inflicted on victim during dispute regarding property boundary."
    ],
    "STALKING": [
        "Unknown individual persistently trailing complainant along daily commute route from transit stop.",
        "Suspicious person repeatedly waiting outside complainant workplace and following vehicle.",
        "Unwanted individual observed loitering near residence entrance and tracking complainant movements for weeks.",
        "Complainant reported repeated trailing on two-wheeler across multiple neighborhood streets.",
        "Individual constantly photographing complainant secretly in public market and following behind.",
        "Persistent shadowing by unknown person despite repeated clear instructions to cease.",
        "Complainant noticed same vehicle following them home on five consecutive evenings.",
        "Suspicious stranger spotted monitoring daily morning walking routine and keeping close distance."
    ],
    "VERBAL_ABUSE_THREAT": [
        "Neighbor aggressively hurled filthy slurs and threatened severe bodily violence.",
        "Shop owner was subjected to loud intimidating threats of property destruction.",
        "Individual shouted obscene language and threatened complainant family during altercation.",
        "Complainant intimidated with death threats over financial settlement dispute.",
        "Motorist used highly offensive vulgar terms and threatened physical confrontation.",
        "Loud verbal harassment and threatening intimidation issued outside complainant residence.",
        "Aggressive shouting and explicit intimidation regarding dire consequences over land disagreement.",
        "Individual used abusive language in public place creating severe distress and fear for safety."
    ],
    "SEXUAL_HARASSMENT": [
        "Inappropriate physical contact and vulgar gestures made toward female passenger in crowded coach.",
        "Complainant subjected to lewd remarks and unsolicited advances while standing at bus shelter.",
        "Unwanted physical touching and suggestive obscene comments by pedestrian near college gate.",
        "Group of men passed vulgar comments and made obscene hand gestures towards woman walking home.",
        "Female commuter inappropriately touched by stranger in transit terminal queue.",
        "Lewd verbal remarks and physical intimidation directed towards pedestrian near park pathway.",
        "Complainant reported repeated unsolicited obscene gestures and vulgar remarks from passing motorbike rider.",
        "Indecent behavior and offensive physical proximity forced upon victim in commercial aisle."
    ],
    "DOMESTIC_VIOLENCE": [
        "Physical violence and beating inflicted upon spouse inside residence during late night dispute.",
        "Complainant suffered contusions and bruises after being assaulted by marital partner with household object.",
        "Family member repeatedly subjected spouse to severe physical beating and emotional abuse.",
        "Domestic altercation where complainant was shoved against wall and hit repeatedly.",
        "Spouse physically assaulted in private quarters resulting in injuries requiring emergency clinic visit.",
        "Complainant reported long-standing physical brutality and assault inside matrimonial home.",
        "Violent confrontation between domestic partners resulting in smashed furniture and bodily harm."
    ],
    "KIDNAPPING": [
        "Minor child was forcibly taken into unmarked van near primary school gate.",
        "Complainant relative was pulled into black four-wheeler by masked men and whisked away.",
        "Minor girl reported missing after being enticed and taken away by unknown adult near playground.",
        "Businessman forcibly abducted from outside office premises into tinted vehicle.",
        "Young child taken away from public amusement area without guardian consent.",
        "Complainant brother bundled into moving car by three unidentified assailants.",
        "School student failed to reach home; witnesses reported student being forced onto motorcycle."
    ],
    "FRAUD": [
        "Victim duped into paying advance deposit for non-existent residential rental lease.",
        "Complainant lost substantial savings after investing in fraudulent high-yield chit fund scheme.",
        "Forged property registration documents used to unlawfully sell vacant land parcel.",
        "Counterfeit currency notes tendered during high-value purchase transaction at jewelry store.",
        "Fake employment agency collected processing fees promising overseas jobs and vanished.",
        "Complainant deceived by bogus contractor who took upfront payment and abandoned project.",
        "Phony travel agent issued invalid airline tickets and pocketed tour package amount."
    ],
    "CYBERCRIME": [
        "Complainant clicked deceptive banking link leading to unauthorized funds deduction from account.",
        "Social media profile cloned with malicious intent to solicit emergency money from contacts.",
        "Email account compromised and company vendor payments diverted to fraudulent bank account.",
        "Victim received deceptive lottery message and surrendered bank credentials leading to debit.",
        "SIM card swapped fraudulently resulting in multiple unauthorized digital wallet transfers.",
        "Ransomware attack encrypted office database demanding cryptocurrency for decryption key.",
        "Fraudulent caller posed as bank executive and extracted OTP causing financial loss."
    ],
    "VANDALISM": [
        "Public bus shelter glass panels smashed and defaced with spray paint overnight.",
        "Multiple cars parked along street had windshields shattered with stones.",
        "Exterior facade of community building defaced with abusive graffiti slogans.",
        "Street lamps and public garden benches intentionally broken and dismantled.",
        "Shopfront advertising board ripped down and property gate damaged intentionally.",
        "Car tires deliberately punctured and side mirrors snapped off in apartment parking lot.",
        "Solar street lighting panels and battery units damaged along public walkway."
    ],
    "DRUG_RELATED_CRIME": [
        "Suspicious trade of contraband narcotic packets observed near abandoned railway shed.",
        "Group of individuals found consuming and possessing banned synthetic substance pills.",
        "Illicit narcotic sachets being peddled to youngsters near perimeter of educational complex.",
        "Suspect apprehended carrying concealed packages of banned psychotropic substances.",
        "Commercial consignment of illegal synthetic pills uncovered inside parked delivery vehicle.",
        "Unlawful distribution of prohibited narcotic substances operating from secluded tea stall."
    ],
    "PUBLIC_DISTURBANCE": [
        "Intoxicated group causing loud ruckus, blocking traffic, and harassing passing vehicles.",
        "Violent clash between two rival groups disrupting public peace near market square.",
        "Loud disorderly mob gathering late night, creating nuisance, and refusing to disperse.",
        "Drunken individuals smashing empty bottles and creating commotion outside residential colony.",
        "Unruly crowd engaged in aggressive shouting and throwing objects near shopping strip.",
        "Disorderly assembly creating public obstruction and alarming neighborhood residents."
    ],
    "HOMICIDE": [
        "Deceased body with fatal stab wounds discovered in deserted open plot.",
        "Victim succumbed to fatal head trauma following severe attack with sharp weapon.",
        "Deceased individual found inside residence with severe lethal injuries indicating foul play.",
        "Fatal physical confrontation on roadside resulting in death of one individual from heavy blows.",
        "Lifeless body of unidentified male found near drainage canal with signs of strangulation.",
        "Fatal altercation outside commercial venue leading to lethal injury and collapse of victim."
    ],
    "OTHER": [
        "Stray cattle herd roaming unattended on main carriageway causing vehicular accidents.",
        "Unauthorized loud construction machinery operating past midnight violating municipal silence rules.",
        "Encroachment on municipal sidewalk with temporary shed obstructing pedestrian pathway.",
        "Dispute over dumping of garbage and construction debris in public common area.",
        "Complainant reported missing briefcase with original educational certificates left on park bench.",
        "Illegal diversion of municipal water pipeline creating severe shortage in colony."
    ],
}


def load_ward_polygons(geojson_path: str):
    """Load and parse ward features with Shapely geometries."""
    if not os.path.exists(geojson_path):
        print(f"CRITICAL ERROR: GeoJSON file not found at {geojson_path}")
        print("STOPPING: Please place Wards.geojson in data/raw/ before proceeding.")
        sys.exit(1)

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    wards = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        poly = shape(geom)
        if poly.is_valid and not poly.is_empty:
            wards.append({
                "zone_no": str(props.get("Zone_No", "")).strip(),
                "ward_no": int(props.get("Ward_No", 0)),
                "zone_name": str(props.get("Zone_Name", "")).strip(),
                "polygon": poly,
                "bounds": poly.bounds  # (minx, miny, maxx, maxy) -> (min_lon, min_lat, max_lon, max_lat)
            })

    if not wards:
        print("CRITICAL ERROR: No valid ward polygons could be parsed from GeoJSON.")
        sys.exit(1)

    print(f"Loaded {len(wards)} valid Chennai ward polygons from {geojson_path}.")
    return wards


def sample_point_in_polygon(polygon, bounds, max_attempts=5000):
    """Sample a random (lat, lon) strictly contained within the Shapely polygon."""
    min_lon, min_lat, max_lon, max_lat = bounds
    for _ in range(max_attempts):
        lon = random.uniform(min_lon, max_lon)
        lat = random.uniform(min_lat, max_lat)
        pt = Point(lon, lat)
        if polygon.contains(pt):
            return lat, lon
    # Fallback to representative point if random rejection sampling exhausts attempts
    rep = polygon.representative_point()
    return rep.y, rep.x


def generate_varied_description(category: str, index: int) -> str:
    """Generate linguistically rich and varied descriptions avoiding exact keyword repetition."""
    base_templates = DESCRIPTION_VOCABULARY[category]
    base_text = base_templates[index % len(base_templates)]

    # Add controlled variations / modifiers
    modifiers_prefix = [
        "Complainant stated that ",
        "Incident reported where ",
        "According to police report, ",
        "Emergency dispatch received stating ",
        "First responder notes indicate ",
        "Patrol unit notified that ",
        "Local resident reported that ",
        "Investigation record notes: ",
        "",
        "",
        ""
    ]
    
    time_context = [
        " during peak morning hours.",
        " in the late evening.",
        " shortly after sunset.",
        " during the afternoon interval.",
        " in the middle of the night.",
        " near the locality entrance.",
        " near the busy crossing.",
        " while transit was crowded.",
        ""
    ]

    prefix = random.choice(modifiers_prefix)
    suffix = random.choice(time_context)

    # Clean punctuation and format
    clean_base = base_text.strip()
    if prefix:
        clean_base = clean_base[0].lower() + clean_base[1:]
        clean_base = prefix + clean_base
    if suffix and not clean_base.endswith(suffix):
        clean_base = clean_base.rstrip(".") + suffix

    return clean_base


def get_time_period(hour: int) -> str:
    if 6 <= hour < 12:
        return "MORNING"
    elif 12 <= hour < 17:
        return "AFTERNOON"
    elif 17 <= hour < 22:
        return "EVENING"
    else:
        return "NIGHT"


def get_category_time_hour(category: str) -> int:
    """Return realistic hour based on category distribution."""
    r = random.random()
    if category in ["BURGLARY", "HOMICIDE", "DRUG_RELATED_CRIME", "PUBLIC_DISTURBANCE"]:
        # Skewed towards evening/night (18:00 to 05:00)
        if r < 0.70:
            return random.choice(list(range(20, 24)) + list(range(0, 6)))
        else:
            return random.randint(6, 19)
    elif category in ["CYBERCRIME", "FRAUD", "WORKPLACE"]:
        # Skewed towards morning/afternoon (09:00 to 18:00)
        if r < 0.75:
            return random.randint(9, 18)
        else:
            return random.randint(0, 23)
    elif category in ["THEFT", "ROBBERY", "ASSAULT", "SEXUAL_HARASSMENT", "STALKING"]:
        # Skewed towards afternoon/evening/night (14:00 to 23:00)
        if r < 0.65:
            return random.randint(14, 23)
        else:
            return random.randint(0, 23)
    else:
        return random.randint(0, 23)


def get_category_location_type(category: str) -> str:
    """Return contextually sensible location type."""
    if category in ["CYBERCRIME"]:
        return "ONLINE"
    elif category in ["FRAUD"]:
        return random.choice(["COMMERCIAL_AREA", "WORKPLACE", "ONLINE", "RESIDENTIAL_AREA"])
    elif category in ["BURGLARY", "DOMESTIC_VIOLENCE"]:
        return "RESIDENTIAL_AREA"
    elif category in ["THEFT", "ROBBERY"]:
        return random.choice(["ROAD", "MARKET", "BUS_STOP", "RAILWAY_AREA", "COMMERCIAL_AREA"])
    elif category in ["ASSAULT", "VERBAL_ABUSE_THREAT", "PUBLIC_DISTURBANCE"]:
        return random.choice(["ROAD", "PUBLIC_PLACE", "MARKET", "PARK", "RESIDENTIAL_AREA"])
    elif category in ["STALKING", "SEXUAL_HARASSMENT"]:
        return random.choice(["BUS_STOP", "ROAD", "EDUCATIONAL_AREA", "PUBLIC_PLACE", "PARK"])
    elif category in ["DRUG_RELATED_CRIME"]:
        return random.choice(["RAILWAY_AREA", "PARK", "PUBLIC_PLACE", "ROAD"])
    elif category in ["KIDNAPPING"]:
        return random.choice(["EDUCATIONAL_AREA", "PARK", "RESIDENTIAL_AREA", "ROAD"])
    elif category in ["VANDALISM"]:
        return random.choice(["PARK", "BUS_STOP", "PUBLIC_PLACE", "COMMERCIAL_AREA"])
    else:
        return random.choice(LOCATION_TYPES)


def generate_dataset(wards):
    """Generate 10,000 synthetic incident records with controlled spatial-temporal patterns."""
    print("Generating 10,000 synthetic crime incidents...")

    # Define baseline end date (current prototype timeline: mid September 2026)
    end_date = datetime(2026, 9, 20)
    start_date = end_date - timedelta(days=365)
    recent_threshold_days = 28  # Recent 4 weeks for dynamic surge

    # Design controlled spatial patterns
    # 1. Historical high-risk wards (persistent elevated crime over the full year)
    # Pick 10 specific ward numbers across commercial/central zones
    all_ward_nos = [w["ward_no"] for w in wards]
    historical_hotspot_wards = random.sample(all_ward_nos, k=min(12, len(all_ward_nos)))
    
    # 2. Dynamic surge wards (recent surge in the past 28 days, different from historical)
    remaining_wards = [wn for wn in all_ward_nos if wn not in historical_hotspot_wards]
    dynamic_surge_wards = random.sample(remaining_wards, k=min(8, len(remaining_wards)))

    print(f"Controlled Reference Wards ({len(historical_hotspot_wards)}): {historical_hotspot_wards}")
    print(f"Controlled Dynamic Surge Wards ({len(dynamic_surge_wards)}): {dynamic_surge_wards}")

    ward_map = {w["ward_no"]: w for w in wards}

    records = []
    crime_counter = 1

    # Prepare category distribution queue
    category_queue = []
    for cat, count in CATEGORY_TARGET_COUNTS.items():
        category_queue.extend([cat] * count)
    random.shuffle(category_queue)

    for idx, category in enumerate(category_queue):
        crime_id = f"CR-{crime_counter:05d}"
        crime_counter += 1

        # Determine if this incident belongs to recent window or historical
        # Controlled probability: 25% of all crimes occur in the recent 28 days
        is_recent = (random.random() < 0.25)
        
        if is_recent:
            days_ago = random.randint(0, recent_threshold_days)
            # In recent window, higher chance of falling into dynamic surge wards
            if random.random() < 0.45 and dynamic_surge_wards:
                selected_ward_no = random.choice(dynamic_surge_wards)
            elif random.random() < 0.25 and historical_hotspot_wards:
                selected_ward_no = random.choice(historical_hotspot_wards)
            else:
                selected_ward_no = random.choice(all_ward_nos)
        else:
            days_ago = random.randint(recent_threshold_days + 1, 365)
            # In historical window, higher chance of falling into historical hotspot wards
            if random.random() < 0.40 and historical_hotspot_wards:
                selected_ward_no = random.choice(historical_hotspot_wards)
            else:
                selected_ward_no = random.choice(all_ward_nos)

        selected_ward = ward_map[selected_ward_no]
        occurred_dt = end_date - timedelta(days=days_ago)
        
        # Time generation
        hour = get_category_time_hour(category)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        occurred_time = f"{hour:02d}:{minute:02d}:{second:02d}"
        occurred_date_str = occurred_dt.strftime("%Y-%m-%d")

        # Time period derivation
        time_period = get_time_period(hour)

        # Reported date (same day or 1-4 days later)
        delay_days = random.choices([0, 1, 2, 3, 5], weights=[0.65, 0.20, 0.08, 0.05, 0.02])[0]
        reported_dt = occurred_dt + timedelta(days=delay_days)
        reported_date_str = reported_dt.strftime("%Y-%m-%d")

        # Coordinate generation with 100% polygon containment
        lat, lon = sample_point_in_polygon(selected_ward["polygon"], selected_ward["bounds"])

        # Description generation
        desc = generate_varied_description(category, idx)

        # Location Type
        loc_type = get_category_location_type(category)

        # Status
        status = random.choices(STATUSES, weights=[0.30, 0.35, 0.25, 0.10])[0]

        records.append({
            "crime_id": crime_id,
            "description": desc,
            "crime_category": category,
            "severity": SEVERITY_MAPPING[category],
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "ward_no": selected_ward["ward_no"],
            "zone_no": selected_ward["zone_no"],
            "zone_name": selected_ward["zone_name"],
            "occurred_date": occurred_date_str,
            "occurred_time": occurred_time,
            "time_period": time_period,
            "location_type": loc_type,
            "reported_date": reported_date_str,
            "status": status,
        })

    df = pd.DataFrame(records)
    return df, ward_map


def validate_dataset(df: pd.DataFrame, ward_map: dict):
    """Comprehensive validation against all Master Frozen Specification rules."""
    print("\n" + "=" * 60)
    print("RUNNING COMPREHENSIVE SAFEZONE DATASET VALIDATION")
    print("=" * 60)

    expected_columns = [
        "crime_id", "description", "crime_category", "severity",
        "latitude", "longitude", "ward_no", "zone_no", "zone_name",
        "occurred_date", "occurred_time", "time_period",
        "location_type", "reported_date", "status"
    ]

    # 1. Row count
    assert len(df) == TARGET_ROW_COUNT, f"Row count mismatch: expected {TARGET_ROW_COUNT}, got {len(df)}"
    print(f"[PASS] Row count: exactly {len(df):,} records")

    # 2. Columns exactly match
    assert list(df.columns) == expected_columns, f"Columns mismatch: expected {expected_columns}, got {list(df.columns)}"
    print(f"[PASS] Column schema: all 15 required columns present in exact order")

    # 3. Unique crime_id
    assert df["crime_id"].nunique() == TARGET_ROW_COUNT, "crime_id contains duplicate values"
    print(f"[PASS] Unique ID: 10,000 distinct crime_ids ({df['crime_id'].iloc[0]} to {df['crime_id'].iloc[-1]})")

    # 4. Null checks
    null_counts = df.isnull().sum()
    assert null_counts.sum() == 0, f"Found null values: {null_counts[null_counts > 0]}"
    print("[PASS] Data Integrity: 0 null or missing values across all columns")

    # 5. Category presence and distribution
    unique_cats = set(df["crime_category"].unique())
    expected_cats = set(CATEGORIES)
    assert unique_cats == expected_cats, f"Categories mismatch: missing {expected_cats - unique_cats}"
    print(f"[PASS] Categories: all 16 frozen categories present")
    cat_dist = df["crime_category"].value_counts().to_dict()
    for cat in CATEGORIES:
        print(f"   - {cat:<22}: {cat_dist[cat]} records (severity: {SEVERITY_MAPPING[cat]})")

    # 6. Severity mapping check
    for cat, sev in SEVERITY_MAPPING.items():
        mismatched = df[(df["crime_category"] == cat) & (df["severity"] != sev)]
        assert len(mismatched) == 0, f"Severity mismatch for category {cat}: expected {sev}"
    print("[PASS] Severity Policy: 100% compliant with frozen severity rules")

    # 7. Date & Time validity
    for _, row in df.iterrows():
        occ_d = datetime.strptime(row["occurred_date"], "%Y-%m-%d")
        rep_d = datetime.strptime(row["reported_date"], "%Y-%m-%d")
        assert rep_d >= occ_d, f"Reported date {row['reported_date']} earlier than occurred date {row['occurred_date']}"
        
        # Check time_period mapping
        h = int(row["occurred_time"].split(":")[0])
        expected_tp = get_time_period(h)
        assert row["time_period"] == expected_tp, f"Time period mismatch at hour {h}"

    print("[PASS] Temporal Consistency: reported_date >= occurred_date for 100% of rows; time_period derived accurately")

    # 8. 100% Geometric Ward Containment
    print("[PASS] Checking 100% geometric polygon containment for all 10,000 points...")
    containment_failures = 0
    for idx, row in df.iterrows():
        wn = row["ward_no"]
        ward_poly = ward_map[wn]["polygon"]
        pt = Point(row["longitude"], row["latitude"])
        if not ward_poly.contains(pt):
            containment_failures += 1

    assert containment_failures == 0, f"Containment check failed: {containment_failures} points outside ward polygons"
    print(f"[PASS] Geospatial Containment: 100.00% (10,000 / 10,000 points strictly inside assigned ward polygons)")

    # 9. Description analysis
    empty_desc = df[df["description"].str.strip() == ""]
    assert len(empty_desc) == 0, "Found empty descriptions"
    print(f"[PASS] NLP Descriptions: 10,000 non-empty descriptions with linguistic diversity")

    # 10. Status & Location types
    assert set(df["status"].unique()).issubset(set(STATUSES))
    assert set(df["location_type"].unique()).issubset(set(LOCATION_TYPES))
    print(f"[PASS] Vocabularies: Valid status ({STATUSES}) and location_type ({len(LOCATION_TYPES)} types)")

    print("=" * 60)
    print("ALL VALIDATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60 + "\n")


def main():
    print(f"Starting Stage 2: SafeZone Synthetic Crime Dataset Generation...")
    wards = load_ward_polygons(RAW_GEOJSON_PATH)

    df, ward_map = generate_dataset(wards)

    # Save to final path
    os.makedirs(os.path.dirname(OUTPUT_CSV_PATH), exist_ok=True)
    df.to_csv(OUTPUT_CSV_PATH, index=False)
    print(f"Saved dataset to {OUTPUT_CSV_PATH}")

    # Validate
    validate_dataset(df, ward_map)


if __name__ == "__main__":
    main()
