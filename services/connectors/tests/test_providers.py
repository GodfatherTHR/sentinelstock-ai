from datetime import datetime, timezone

import pytest

from app.providers import NormalizedSentimentObservation, NormalizedShippingEvent, validate_aggregate_sentiment, validate_shipping_event


def test_privacy_preserving_signal_validation():
    validate_aggregate_sentiment(NormalizedSentimentObservation("Dhaka", "Staples", .6, .1, .7, .9, 120))


def test_invalid_shipping_risk_is_rejected():
    event = NormalizedShippingEvent("shp-1", "provider", "vessel", 23.8, 90.4, "Dhaka", datetime.now(timezone.utc), "in_transit", 1.2)
    with pytest.raises(ValueError):
        validate_shipping_event(event)
