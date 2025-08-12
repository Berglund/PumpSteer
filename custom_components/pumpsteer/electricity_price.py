# FIXED electricity_price.py - Correct database access for Home Assistant 2025

import logging
from datetime import datetime, timedelta
from typing import Dict, List

import numpy as np
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import now as dt_now

from .settings import (
    ABSOLUTE_CHEAP_LIMIT,
    CHEAP_MULTIPLIER,
    DEFAULT_EXTREME_MULTIPLIER,
    DEFAULT_PERCENTILES,
    DEFAULT_TRAILING_HOURS,
    EXPENSIVE_MULTIPLIER,
    MAX_PRICE_WARNING_THRESHOLD,
    MIN_SAMPLES_FOR_CLASSIFICATION,
    NORMAL_MULTIPLIER,
    PRICE_CATEGORIES,
)

# — Legacy/Configuration Section (Settings imported from another file) —

# These settings are typically defined elsewhere and represent configurable
# parameters for price classification. Depending on the project's evolution,
# these might be considered part of the 'legacy' configuration if not actively
# maintained or if they represent initial fixed values.


_LOGGER = logging.getLogger(__name__)


def validate_price_list(price_list: List[float], min_samples: int = MIN_SAMPLES_FOR_CLASSIFICATION) -> bool:
    """
    Validate that a price list is suitable for classification.
    This function ensures the input price list is not empty, contains enough
    samples, and only has numeric values. It also logs warnings for
    unexpected data, like negative or extremely high prices.
    """
    if not price_list or len(price_list) < min_samples:
        return False

    # Check for None values in the list
    if any(p is None for p in price_list):
        _LOGGER.warning("Found None values in price list")
        return False

    # Ensure all values can be converted to floats (are numeric)
    try:
        float_prices = [float(p) for p in price_list]
    except (ValueError, TypeError) as e:
        _LOGGER.error(f"Non-numeric values found in price list: {e}")
        return False

    # Log warnings for unusual (but not necessarily invalid) price values
    negative_prices = [p for p in float_prices if p < 0]
    if negative_prices:
        _LOGGER.warning(f"Found {len(negative_prices)} negative prices in dataset")

    extreme_prices = [p for p in float_prices if p > MAX_PRICE_WARNING_THRESHOLD]
    if extreme_prices:
        _LOGGER.warning(f"Found {len(extreme_prices)} extremely high prices (>{MAX_PRICE_WARNING_THRESHOLD} kr/kWh)")

    return True


def classify_prices(price_list: List[float], percentiles: List[float] = None) -> List[str]:
    """
    Classify prices into categories (e.g., "very_cheap", "cheap", "normal", "expensive", "very_expensive")
    based on percentile thresholds calculated from the price list itself.
    This is a purely statistical classification based on the distribution of the current prices.
    """
    if percentiles is None:
        percentiles = DEFAULT_PERCENTILES

    # Validate the input price list before attempting classification
    if not validate_price_list(price_list):
        _LOGGER.debug(f"Invalid price list for classification (length: {len(price_list) if price_list else 0})")
        # Return "unknown" categories if the list is invalid
        return ["unknown"] * len(price_list) if price_list else []

    if len(percentiles) != 4:
        raise ValueError("Exactly 4 percentiles required for 5-category classification")

    price_array = np.array(price_list)

    # Filter out negative prices for percentile calculation
    positive_prices = price_array[price_array >= 0]

    # Calculate thresholds only for non-negative prices
    if len(positive_prices) > 0:
        thresholds = np.percentile(positive_prices, percentiles)
    else:
        # If all prices are negative, all are classified as 'negative_price'
        return ["negative_price"] * len(price_list)

    # Use NumPy for efficient classification based on thresholds
    categories_positive = np.select(
        [
            positive_prices < thresholds[0],  # Prices below the first percentile threshold
            positive_prices < thresholds[1],  # Prices between the first and second
            positive_prices < thresholds[2],  # Prices between the second and third
            positive_prices < thresholds[3]   # Prices between the third and fourth
        ],
        ["very_cheap", "cheap", "normal", "expensive"],  # Categories for the above conditions
        default="very_expensive"  # Default category for prices above the last threshold
    )

    # Create the final result list by combining negative and positive classifications
    final_categories = []
    positive_index = 0
    for price in price_list:
        if price < 0:
            final_categories.append("negative_price")
        else:
            final_categories.append(categories_positive[positive_index])
            positive_index += 1

    return final_categories


async def async_hybrid_classify_with_history(
    hass: HomeAssistant,
    price_list: List[float],
    price_entity_id: str,
    trailing_hours: int = DEFAULT_TRAILING_HOURS
) -> List[str]:
    """
    Classify prices using a hybrid approach that incorporates historical data from Home Assistant.
    It fetches historical prices for a given `trailing_hours` period, calculates an average
    from them, and then classifies current `price_list` entries relative to this historical average.
    This provides a more dynamic classification than just percentile-based.
    """
    if not price_list or len(price_list) < MIN_SAMPLES_FOR_CLASSIFICATION:
        # If the current price list is invalid, return "unknown" categories
        return ["unknown"] * len(price_list)

    end_time = dt_now()  # Current time
    start_time = end_time - timedelta(hours=trailing_hours)  # Start time for historical data fetch

    try:
        recorder = get_instance(hass)

        def get_price_history():
            return get_significant_states(
                hass,
                start_time,
                end_time,
                [price_entity_id]
            )

        history = await recorder.async_add_executor_job(get_price_history)

        states = history.get(price_entity_id, [])  # Extract states for the specific entity
        trailing_prices = []

        # Process historical states to extract valid numeric prices
        for s in states:
            try:
                if s.state not in ("unknown", "unavailable"):
                    trailing_prices.append(float(s.state))
            except (ValueError, TypeError):
                _LOGGER.debug(f"Skipping invalid state value from history: {s.state}")
                continue

        # Calculate the average price from the retrieved historical data
        if not trailing_prices:
            _LOGGER.warning("Could not retrieve trailing prices; fallback to daily average of current list.")
            avg_price = get_daily_average(price_list)  # Fallback to current list average if history fails
        else:
            avg_price = get_daily_average(trailing_prices)  # Use historical average

        _LOGGER.debug(f"Retrieved {len(trailing_prices)} trailing prices from history")
        _LOGGER.debug(f"Trailing average: {avg_price}")

    except Exception as e:
        _LOGGER.error(f"Error retrieving price history: {e}")
        avg_price = get_daily_average(price_list)  # Fallback to current list average on error

    # Fallback to standard percentile classification if the calculated average is invalid (e.g., zero)
    if avg_price <= 0:
        _LOGGER.warning("Invalid average price calculated from history; using standard percentile classification.")
        return classify_prices(price_list)

    # Classify current prices based on the calculated historical average and predefined multipliers
    result = []
    for price in price_list:
        # --- START REVISED LOGIC ---
        # First, check for negative prices as a special case
        if price < 0:
            result.append("negative_price")
        # Then, apply the original logic for non-negative prices
        elif price <= 0.20:
            result.append("very_cheap")
        elif price <= 0.50:
            result.append("cheap")
        elif price <= avg_price * CHEAP_MULTIPLIER:
            result.append("cheap")
        elif price < avg_price * NORMAL_MULTIPLIER:
            # This is a specific 'hybrid' rule: if the price is below NORMAL_MULTIPLIER
            # but also below an ABSOLUTE_CHEAP_LIMIT, it's still classified as "cheap".
            # This blends relative (to average) and absolute thresholds.
            result.append("cheap" if price < ABSOLUTE_CHEAP_LIMIT else "normal")
        elif price < avg_price * EXPENSIVE_MULTIPLIER:
            result.append("expensive")
        else:
            result.append("very_expensive")
        # --- END REVISED LOGIC ---

    return result


def get_daily_average(price_list: List[float]) -> float:
    """
    Calculate the average of a list of prices.
    """
    if not price_list:
        return 0.0
    return round(sum(price_list) / len(price_list), 3)


def get_price_statistics(price_list: List[float]) -> Dict[str, float]:
    """
    Calculate various descriptive statistics for a list of prices.
    Includes average, median, minimum, maximum, and standard deviation.
    """
    if not price_list:
        return {"average": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}

    # Filter out negative prices before calculating statistics to avoid skewing
    positive_prices = [p for p in price_list if p >= 0]
    if not positive_prices:
        # Handle case where all prices are negative
        return {"average": 0.0, "median": 0.0, "min": min(price_list), "max": max(price_list), "std": 0.0}

    return {
        "average": round(np.mean(positive_prices), 3),
        "median": round(np.median(positive_prices), 3),
        "min": round(min(price_list), 3),  # Keep original min, as it can be negative
        "max": round(max(price_list), 3),
        "std": round(np.std(positive_prices), 3)
    }


def is_extreme(price: float, price_list: List[float], multiplier: float = DEFAULT_EXTREME_MULTIPLIER) -> bool:
    """
    Check if a single price is considered "extreme" relative to the average of a given price list.
    An extreme price is defined as exceeding the average by a certain multiplier.
    """
    avg = get_daily_average([p for p in price_list if p >= 0])  # Calculate average only for non-negative prices
    if avg <= 0.0:
        return False
    return price > avg * multiplier


def count_categories(price_list: List[float]) -> Dict[str, int]:
    """
    Count the occurrences of each price category (e.g., "very_cheap", "expensive")
    after classifying all prices in the input list using the `classify_prices` function.
    """
    categories = classify_prices(price_list)
    # Initialize counts for all possible categories, including 'unknown'
    counts = {category: 0 for category in PRICE_CATEGORIES}
    counts["unknown"] = 0
    counts["negative_price"] = 0

    for category in categories:
        counts[category] += 1

    return counts


def count_category(price_list: List[float], target_category: str) -> int:
    """
    Count the occurrences of a specific price category within a list of prices.
    """
    valid_categories = PRICE_CATEGORIES + ["unknown", "negative_price"]

    if target_category not in valid_categories:
        raise ValueError(f"Unknown category: {target_category}. Valid categories: {valid_categories}")

    categories = classify_prices(price_list)
    return categories.count(target_category)


def find_cheapest_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Find the indices (positions) of the `num_hours` cheapest prices in the list.
    The indices correspond to the original position in the `price_list`.
    """
    if not price_list or num_hours <= 0:
        return []

    # Pair each price with its original index
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    # Sort by price in ascending order
    indexed_prices.sort(key=lambda x: x[1])
    # Return the indices of the cheapest hours
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]


def find_most_expensive_hours(price_list: List[float], num_hours: int = 1) -> List[int]:
    """
    Find the indices (positions) of the `num_hours` most expensive prices in the list.
    The indices correspond to the original position in the `price_list`.
    """
    if not price_list or num_hours <= 0:
        return []

    # Pair each price with its original index
    indexed_prices = [(i, price) for i, price in enumerate(price_list)]
    # Sort by price in descending order
    indexed_prices.sort(key=lambda x: x[1], reverse=True)
    # Return the indices of the most expensive hours
    return [i for i, _ in indexed_prices[:min(num_hours, len(indexed_prices))]]


# — ADDED: New PumpSteer-specific functions —

async def async_get_forecast_prices(
    hass: HomeAssistant,
    price_entity_id: str,
    hours_ahead: int = 6
) -> List[Dict[str, any]]:
    """
    Retrieve future electricity prices for PumpSteer's 6-hour forecast.
    """
    try:
        # Get entity's attributes which often contain future prices
        state = hass.states.get(price_entity_id)
        if not state:
            _LOGGER.warning(f"Could not find entity: {price_entity_id}")
            return []

        # Many electricity price integrations store future prices in attributes
        raw_prices = state.attributes.get('raw_today', []) + state.attributes.get('raw_tomorrow', [])

        if not raw_prices:
            _LOGGER.debug("No future prices found in entity attributes")
            return []

        # Filter only future hours
        current_time = dt_now()
        forecast_prices = []

        for price_data in raw_prices:
            if isinstance(price_data, dict) and 'start' in price_data and 'value' in price_data:
                try:
                    # Convert start time to datetime if needed
                    start_time = price_data['start']
                    if isinstance(start_time, str):
                        # `datetime` is already imported at the top
                        start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))

                    # Only future prices
                    if start_time > current_time:
                        forecast_prices.append({
                            'timestamp': start_time,
                            'price': float(price_data['value']),
                            'hours_from_now': int((start_time - current_time).total_seconds() / 3600)
                        })

                        # Limit to desired number of hours
                        if len(forecast_prices) >= hours_ahead:
                            break

                except (ValueError, TypeError, KeyError) as e:
                    _LOGGER.debug(f"Skipping invalid price data: {e}")
                    continue

        # Sort by time
        forecast_prices.sort(key=lambda x: x['timestamp'])
        return forecast_prices[:hours_ahead]

    except Exception as e:
        _LOGGER.error(f"Error retrieving forecast prices: {e}")
        return []


def calculate_boost_potential(
    current_prices: List[float],
    forecast_prices: List[Dict[str, any]],
    aggressiveness: int = 3
) -> Dict[str, any]:
    """
    Calculate boost potential based on current and future prices.
    """
    if not current_prices or not forecast_prices:
        return {
            'should_boost': False,
            'boost_hours': 0,
            'reason': 'Insufficient price data'
        }

    current_avg = get_daily_average(current_prices)
    future_prices = [p['price'] for p in forecast_prices]
    future_avg = get_daily_average(future_prices)

    # Aggressiveness multipliers (the higher the aggressiveness, the more boost)
    aggressiveness_multipliers = {
        0: 0.5,    # Very conservative
        1: 0.7,    # Conservative
        2: 0.85,   # Moderate
        3: 1.0,    # Normal
        4: 1.2,    # Aggressive
        5: 1.5     # Very aggressive
    }

    multiplier = aggressiveness_multipliers.get(aggressiveness, 1.0)

    # Check if future prices are significantly higher
    price_increase_threshold = current_avg * (1.2 * multiplier)

    if future_avg > price_increase_threshold:
        # Find the cheapest hours now for boosting
        cheap_hours = find_cheapest_hours(current_prices, max(1, aggressiveness))

        return {
            'should_boost': True,
            'boost_hours': len(cheap_hours),
            'boost_indices': cheap_hours,
            'current_avg': current_avg,
            'future_avg': future_avg,
            'savings_potential': future_avg - current_avg,
            'reason': f'Future prices {future_avg:.3f} > threshold {price_increase_threshold:.3f}'
        }

    return {
        'should_boost': False,
        'boost_hours': 0,
        'reason': f'Future prices {future_avg:.3f} <= threshold {price_increase_threshold:.3f}'
    }
