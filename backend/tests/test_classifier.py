import pytest
from app.ml.crime_classifier import CrimeClassifier, classify_crime_description

FROZEN_CATEGORIES = [
    "THEFT",
    "ROBBERY",
    "BURGLARY",
    "ASSAULT",
    "STALKING",
    "VERBAL_ABUSE_THREAT",
    "SEXUAL_HARASSMENT",
    "DOMESTIC_VIOLENCE",
    "KIDNAPPING",
    "FRAUD",
    "CYBERCRIME",
    "VANDALISM",
    "DRUG_RELATED_CRIME",
    "PUBLIC_DISTURBANCE",
    "HOMICIDE",
    "OTHER",
]


def test_classifier_initialization():
    classifier = CrimeClassifier.get_instance()
    assert classifier.is_ready(), "CrimeClassifier should successfully load saved artifacts"
    assert len(classifier.classes) == 16
    assert set(classifier.classes) == set(FROZEN_CATEGORIES)


def test_classify_theft_description():
    # Novel description not verbatim in training set
    desc = "My bicycle that was locked to the station rail was stolen during peak transit hours."
    result = classify_crime_description(desc)
    assert result["predicted_category"] in FROZEN_CATEGORIES
    assert result["predicted_category"] == "THEFT"
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["classification_status"] in ["AUTO_CLASSIFIED", "REVIEW_REQUIRED"]


def test_classify_burglary_description():
    desc = "Intruders broke the rear window padlock overnight and ransacked the bedroom jewelry safe."
    result = classify_crime_description(desc)
    assert result["predicted_category"] == "BURGLARY"
    assert result["confidence"] >= 0.75
    assert result["classification_status"] == "AUTO_CLASSIFIED"


def test_classify_cybercrime_description():
    desc = "Clicked an email phishing link which resulted in an unauthorized money transfer from bank account."
    result = classify_crime_description(desc)
    assert result["predicted_category"] == "CYBERCRIME"
    assert result["confidence"] >= 0.75
    assert result["classification_status"] == "AUTO_CLASSIFIED"


def test_classify_homicide_description():
    desc = "A deceased body with fatal trauma was discovered in an isolated vacant lot."
    result = classify_crime_description(desc)
    assert result["predicted_category"] == "HOMICIDE"
    assert result["confidence"] >= 0.75
    assert result["classification_status"] == "AUTO_CLASSIFIED"


def test_low_confidence_or_ambiguous_text():
    # Ambiguous / nonsensical text with no clear crime indicators
    desc = "random words xyz hello sky blue tomorrow morning walking"
    result = classify_crime_description(desc)
    assert result["predicted_category"] in FROZEN_CATEGORIES
    assert 0.0 <= result["confidence"] <= 1.0


def test_empty_description_handling():
    result = classify_crime_description("")
    assert result["classification_status"] == "REVIEW_REQUIRED"
    assert result["predicted_category"] in FROZEN_CATEGORIES
